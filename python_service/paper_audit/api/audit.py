from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any
import tempfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from uuid import uuid4

from ..config import settings
from ..core import rust_client
from ..core.task_queue import TaskQueue

router = APIRouter()
_task_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_TASKS)
logger = logging.getLogger(__name__)


def _decode_checkpoint(task: dict[str, Any] | None) -> dict[str, Any]:
    if not task:
        return {}
    raw = task.get("checkpoint_data")
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


async def _save_checkpoint(
    tq: TaskQueue,
    task_id: int,
    checkpoint: dict[str, Any],
    *,
    current_stage: str,
    progress: int,
) -> None:
    await tq.update_task(
        task_id,
        current_stage=current_stage,
        progress=progress,
        checkpoint_data=json.dumps(checkpoint, ensure_ascii=False),
    )


def _parse_font_size(value: Any, default: float = 12.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"(\d+(?:\.\d+)?)", value)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
    return default


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


class FontManager:
    def __init__(self) -> None:
        self._font_stack = self._build_font_stack()
        self._resolved_file_cache: dict[tuple[str, bool], str | None] = {}

    def _build_font_stack(self) -> list[Path]:
        project_root = Path(__file__).resolve().parents[3]
        candidates = [
            settings.CUSTOM_FONT_DIR,
            project_root / "assets" / "fonts",
            Path.home() / ".fonts",
            Path("/usr/share/fonts"),
            Path("/System/Library/Fonts"),
            Path(r"C:\Windows\Fonts"),
        ]
        return [
            candidate for candidate in candidates if candidate and candidate.exists()
        ]

    @staticmethod
    def _is_cjk_text(text: str) -> bool:
        return any("\u4e00" <= char <= "\u9fff" for char in text)

    def _candidate_names(self, preferred_font: str | None, text: str) -> list[str]:
        preferred = (preferred_font or "").lower()
        if "黑体" in preferred or "hei" in preferred:
            return [
                "simhei.ttf",
                "simhei.ttc",
                "wqy-zenhei.ttc",
                "wqy-zenhei.ttf",
                "NotoSansCJK-Regular.ttc",
                "NotoSansCJK-Regular.otf",
                "NotoSansCJKsc-Regular.otf",
                "simsun.ttc",
                "simsun.ttf",
            ]
        if "宋体" in preferred or "song" in preferred or "serif" in preferred:
            return [
                "simsun.ttc",
                "simsun.ttf",
                "wqy-microhei.ttc",
                "wqy-microhei.ttf",
                "NotoSerifCJK-Regular.ttc",
                "NotoSerifCJK-Regular.otf",
                "NotoSerifCJKsc-Regular.otf",
                "NotoSansCJK-Regular.ttc",
                "NotoSansCJK-Regular.otf",
            ]
        if self._is_cjk_text(text):
            return [
                "wqy-microhei.ttc",
                "wqy-microhei.ttf",
                "wqy-zenhei.ttc",
                "wqy-zenhei.ttf",
                "NotoSansCJK-Regular.ttc",
                "NotoSansCJK-Regular.otf",
                "NotoSerifCJK-Regular.ttc",
                "NotoSerifCJK-Regular.otf",
                "simsun.ttc",
                "simsun.ttf",
                "simhei.ttf",
            ]
        return []

    def _candidate_paths(self, preferred_font: str | None, text: str) -> list[Path]:
        candidate_names = self._candidate_names(preferred_font, text)
        if not candidate_names:
            return []

        candidate_paths: list[Path] = []
        for root in self._font_stack:
            if root.is_file():
                candidate_paths.append(root)
                continue
            for candidate_name in candidate_names:
                candidate_path = root / candidate_name
                if candidate_path.exists():
                    candidate_paths.append(candidate_path)
            if candidate_paths:
                break

        return candidate_paths

    def resolve(self, preferred_font: str | None, text: str) -> tuple[str, str | None]:
        cache_key = ((preferred_font or "").lower(), self._is_cjk_text(text))
        cached = self._resolved_file_cache.get(cache_key)
        if cached is not None or cache_key in self._resolved_file_cache:
            return self._font_name_for(preferred_font, cached), cached

        candidate_paths = self._candidate_paths(preferred_font, text)
        resolved = str(candidate_paths[0]) if candidate_paths else None
        self._resolved_file_cache[cache_key] = resolved
        return self._font_name_for(preferred_font, resolved), resolved

    @staticmethod
    def _font_name_for(preferred_font: str | None, resolved_path: str | None) -> str:
        if resolved_path:
            name = Path(resolved_path).stem.strip()
            if name:
                return name
        preferred = (preferred_font or "").strip()
        if preferred:
            return preferred
        return "helv"


_FONT_MANAGER = FontManager()


def _resolve_cjk_font_file(font_name: str | None = None) -> str | None:
    return _FONT_MANAGER.resolve(font_name, "测试")[1]


def _extract_parsed_data(report_payload: dict[str, Any]) -> dict[str, Any]:
    parse_result = report_payload.get("parse_result")
    if isinstance(parse_result, dict):
        nested = parse_result.get("data")
        if isinstance(nested, dict):
            return nested
        return parse_result
    return {}


def _extract_sections(parsed_data: dict[str, Any]) -> list[dict[str, Any]]:
    sections = parsed_data.get("sections", []) if isinstance(parsed_data, dict) else []
    return [section for section in sections if isinstance(section, dict)]


def _normalize_pdf_text(value: Any) -> str:
    return _normalize_text(value)


def _build_pdf_section_page_map(
    doc: Any, sections: list[dict[str, Any]]
) -> dict[int, int]:
    page_texts = [
        _normalize_pdf_text(page.get_text("text")) if page is not None else ""
        for page in doc
    ]
    section_page_map: dict[int, int] = {}
    last_matched_page_index = 0

    for section in sections:
        section_id = section.get("id")
        if not isinstance(section_id, int):
            continue

        raw_text = str(section.get("raw_text") or section.get("text") or "").strip()
        if not raw_text:
            continue

        normalized_section_text = _normalize_pdf_text(raw_text)
        if not normalized_section_text:
            continue

        page_number: int | None = None
        search_order = list(range(last_matched_page_index, len(page_texts)))
        if last_matched_page_index > 0:
            search_order.extend(range(0, last_matched_page_index))

        for page_index in search_order:
            page_text = page_texts[page_index]
            if normalized_section_text in page_text:
                page_number = page_index + 1
                last_matched_page_index = page_index
                break

        if page_number is None:
            coordinates = _section_coordinates(section)
            if coordinates and isinstance(coordinates.get("page"), int):
                page_number = int(coordinates["page"])
            else:
                page_number = 1

        section_page_map[section_id] = page_number

    return section_page_map


def _section_coordinates(section: dict[str, Any]) -> dict[str, float] | None:
    coordinates = section.get("coordinates")
    if not isinstance(coordinates, dict):
        return None

    page = coordinates.get("page")
    x = coordinates.get("x")
    y = coordinates.get("y")
    width = coordinates.get("width")
    height = coordinates.get("height")
    numeric_values = (page, x, y, width, height)
    if not all(isinstance(value, (int, float)) for value in numeric_values):
        return None

    return {
        "page": int(page),
        "x": float(x),
        "y": float(y),
        "width": float(width),
        "height": float(height),
    }


def _build_section_index(sections: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    section_index: dict[int, dict[str, Any]] = {}
    for section in sections:
        section_id = section.get("id")
        if isinstance(section_id, int):
            section_index[section_id] = section
    return section_index


def _reference_section_for_text(
    reference_text: str, sections: list[dict[str, Any]]
) -> dict[str, Any] | None:
    normalized_reference = _normalize_text(reference_text)
    if not normalized_reference:
        return None

    reference_head = normalized_reference[:120]
    for section in sections:
        raw_text = section.get("raw_text") or section.get("text") or ""
        normalized_section = _normalize_text(raw_text)
        if not normalized_section:
            continue
        if normalized_reference in normalized_section:
            return section
        if reference_head and reference_head in normalized_section:
            return section
        if normalized_section in normalized_reference:
            return section
    return None


def _candidate_page_numbers(page_number: int, total_pages: int) -> list[int]:
    candidates: list[int] = []

    def add(page: int) -> None:
        if 1 <= page <= total_pages and page not in candidates:
            candidates.append(page)

    add(page_number)
    add(page_number - 1)
    add(page_number + 1)

    for offset in range(2, total_pages + 1):
        add(page_number - offset)
        add(page_number + offset)

    return candidates


def _rect_center_distance(rect: Any, preferred_rect: dict[str, float] | None) -> float:
    if not preferred_rect:
        return 0.0
    rect_center_x = float((rect.x0 + rect.x1) / 2.0)
    rect_center_y = float((rect.y0 + rect.y1) / 2.0)
    preferred_center_x = preferred_rect["x"] + preferred_rect["width"] / 2.0
    preferred_center_y = preferred_rect["y"] + preferred_rect["height"] / 2.0
    return abs(rect_center_x - preferred_center_x) + abs(
        rect_center_y - preferred_center_y
    )


def _search_text_rect_on_page(
    page: Any, target_text: str, preferred_rect: dict[str, float] | None = None
) -> Any | None:
    import fitz

    normalized_target = _normalize_text(target_text)
    if not normalized_target:
        return None

    search_variants: list[str] = []
    for variant in (
        target_text,
        re.sub(r"\s+", " ", str(target_text or "")).strip(),
    ):
        if variant and variant not in search_variants:
            search_variants.append(variant)

    best_rect: Any | None = None
    best_score: float | None = None

    for variant in search_variants:
        try:
            matches = page.search_for(variant)
        except Exception:
            matches = []
        for rect in matches:
            score = _rect_center_distance(rect, preferred_rect)
            if best_score is None or score < best_score:
                best_rect = rect
                best_score = score

    if best_rect is not None:
        return best_rect

    try:
        words = page.get_text("words", sort=True)
    except Exception:
        words = []

    token_entries: list[tuple[str, Any]] = []
    for word in words:
        if len(word) < 5:
            continue
        token_text = _normalize_text(word[4])
        if not token_text:
            continue
        token_entries.append(
            (token_text, fitz.Rect(word[0], word[1], word[2], word[3]))
        )

    if not token_entries:
        return None

    concatenated_text = "".join(token_text for token_text, _ in token_entries)
    if normalized_target not in concatenated_text:
        return None

    token_ranges: list[tuple[int, int]] = []
    cursor = 0
    for token_text, _ in token_entries:
        start = cursor
        cursor += len(token_text)
        token_ranges.append((start, cursor))

    candidate_rects: list[Any] = []
    start_index = 0
    while True:
        match_index = concatenated_text.find(normalized_target, start_index)
        if match_index < 0:
            break
        match_end = match_index + len(normalized_target)
        start_token_index = None
        end_token_index = None
        for token_index, (token_start, token_end) in enumerate(token_ranges):
            if start_token_index is None and token_end > match_index:
                start_token_index = token_index
            if token_start < match_end:
                end_token_index = token_index
        if start_token_index is not None and end_token_index is not None:
            rect = token_entries[start_token_index][1]
            for token_index in range(start_token_index + 1, end_token_index + 1):
                rect = rect | token_entries[token_index][1]
            candidate_rects.append(rect)
        start_index = match_index + 1

    if not candidate_rects:
        return None

    if preferred_rect:
        candidate_rects.sort(
            key=lambda rect: _rect_center_distance(rect, preferred_rect)
        )
    else:
        candidate_rects.sort(key=lambda rect: (rect.y0, rect.x0))

    return candidate_rects[0]


def _find_section_rect_on_pdf(
    doc: Any,
    section: dict[str, Any],
    page_number_hint: int,
) -> tuple[int, Any] | None:
    raw_text = str(section.get("raw_text") or section.get("text") or "").strip()
    if not raw_text:
        return None

    preferred_rect = _section_coordinates(section)
    page_numbers = _candidate_page_numbers(page_number_hint, len(doc))
    for page_number in page_numbers:
        page = doc[page_number - 1]
        rect = _search_text_rect_on_page(page, raw_text, preferred_rect)
        if rect is not None:
            return page_number, rect
    return None


def _format_issue_note(section_id: int, issue: dict[str, Any]) -> str:
    issue_type = str(issue.get("issue_type") or "issue").strip()
    message = str(issue.get("message") or "").strip()
    suggestion = str(issue.get("suggestion") or "").strip()
    parts = [f"§{section_id}", issue_type]
    if message:
        parts.append(message)
    if suggestion and suggestion != message:
        parts.append(suggestion)
    return (
        "：".join(parts[:2])
        + (f" {message}" if message else "")
        + (f"（{suggestion}）" if suggestion and suggestion != message else "")
    )


def _format_reference_note(index: int, entry: dict[str, Any]) -> str:
    verdict = str(entry.get("verdict") or "unverified").strip()
    reason = str(entry.get("reason") or "").strip()
    note = f"参考{index} {verdict}"
    if reason:
        note = f"{note}：{reason}"
    return note


def _freeze_issue_value(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(
            sorted((str(key), _freeze_issue_value(item)) for key, item in value.items())
        )
    if isinstance(value, list):
        return tuple(_freeze_issue_value(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted(_freeze_issue_value(item) for item in value))
    return value


def _issue_signature(issue: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(issue.get("issue_type") or ""),
        str(issue.get("field_name") or ""),
        str(issue.get("original") or "").strip(),
        str(issue.get("message") or "").strip(),
        str(issue.get("suggestion") or "").strip(),
        str(issue.get("rule_id") or "").strip(),
        issue.get("severity"),
        _freeze_issue_value(issue.get("position")),
    )


def _dedupe_issue_list(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        signature = _issue_signature(issue)
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(issue)
    return deduped


def _compact_chunk_review_for_report(chunk_review: dict[str, Any]) -> dict[str, Any]:
    compacted = dict(chunk_review)
    issue_views: dict[str, list[dict[str, Any]]] = {}

    for key in ("local_issues", "llm_issues", "table_issues", "issues"):
        value = compacted.get(key)
        if isinstance(value, list):
            issue_views[key] = _dedupe_issue_list(
                [issue for issue in value if isinstance(issue, dict)]
            )

    if issue_views:
        merged_issues = issue_views.get("issues", [])
        if not merged_issues:
            merged_issues = _dedupe_issue_list(
                [
                    *issue_views.get("local_issues", []),
                    *issue_views.get("llm_issues", []),
                    *issue_views.get("table_issues", []),
                ]
            )
        compacted["issues"] = merged_issues
        compacted["issue_count"] = len(merged_issues)

        for key in ("local_issues", "llm_issues", "table_issues"):
            current = issue_views.get(key, [])
            if not current or current == merged_issues:
                compacted.pop(key, None)
            else:
                compacted[key] = current

    if isinstance(compacted.get("row_reviews"), list):
        compacted["row_reviews"] = [
            (
                _compact_chunk_review_for_report(row_review)
                if isinstance(row_review, dict)
                else row_review
            )
            for row_review in compacted["row_reviews"]
        ]

    return compacted


def _compact_ai_review_for_report(ai_review: dict[str, Any]) -> dict[str, Any]:
    compacted = dict(ai_review)
    chunk_reviews = compacted.get("chunk_reviews")
    if isinstance(chunk_reviews, list):
        compacted["chunk_reviews"] = [
            (
                _compact_chunk_review_for_report(chunk_review)
                if isinstance(chunk_review, dict)
                else chunk_review
            )
            for chunk_review in chunk_reviews
        ]
    return compacted


def _estimate_page_size(
    max_right: float, max_bottom: float, note_count: int
) -> tuple[float, float, float, float]:
    page_margin = 24.0
    sidebar_gap = 16.0
    sidebar_width = 220.0
    page_width = max(max_right + sidebar_gap + sidebar_width + page_margin, 680.0)
    page_height = max(max_bottom + 120.0, float(note_count) * 56.0 + 120.0, 842.0)
    sidebar_x = max_right + sidebar_gap
    return page_width, page_height, sidebar_x, page_margin


def _issue_severity_score(issue: dict[str, Any]) -> float:
    severity = issue.get("severity")
    if isinstance(severity, (int, float)):
        return float(severity)
    if isinstance(severity, str):
        value = severity.strip().lower()
        mapping = {
            "critical": 4.0,
            "high": 3.0,
            "medium": 2.0,
            "normal": 2.0,
            "low": 1.0,
            "info": 0.0,
        }
        if value in mapping:
            return mapping[value]
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _issue_sort_key(issue: dict[str, Any]) -> tuple[float, float, str, str]:
    return (
        -_issue_severity_score(issue),
        float(issue.get("y", 0.0)),
        str(issue.get("issue_type") or ""),
        str(issue.get("message") or ""),
    )


def _calculate_annotation_layout(
    page_issues: list[dict[str, Any]], page_height: float, page_width: float
) -> dict[str, Any]:
    sorted_issues = sorted(page_issues, key=_issue_sort_key)
    note_height = 42.0
    usable_height = max(page_height * 0.8, note_height)
    max_visible = max(1, int(usable_height / note_height))
    sidebar_width = min(max(200.0, len(sorted_issues) * 15.0), page_width * 0.35)

    if len(sorted_issues) > max_visible:
        return {
            "mode": "summary",
            "sidebar_width": sidebar_width,
            "content_width": page_width - sidebar_width - 32.0,
            "show_top_n": max_visible,
            "overflow_count": len(sorted_issues) - max_visible,
            "visible_issues": sorted_issues[:max_visible],
        }

    return {
        "mode": "sidebar",
        "sidebar_width": sidebar_width,
        "content_width": page_width - sidebar_width - 32.0,
        "show_top_n": len(sorted_issues),
        "overflow_count": 0,
        "visible_issues": sorted_issues,
    }


def _format_overflow_note(overflow_count: int) -> str:
    return f"本页还有 {overflow_count} 条问题已折叠，请查看 JSON 报告或原始任务详情。"


def _pdf_text_length(pdf_path: Path) -> int:
    import fitz

    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return 0

    try:
        return sum(len(page.get_text("text").strip()) for page in doc)
    finally:
        doc.close()


def _pdf_has_meaningful_content(pdf_path: Path, *, min_text_length: int = 20) -> bool:
    return (
        pdf_path.exists()
        and pdf_path.is_file()
        and _pdf_text_length(pdf_path) >= min_text_length
    )


def _resolve_libreoffice_converter() -> tuple[str | None, list[str]]:
    warnings: list[str] = []
    env_candidates = [
        os.environ.get("LIBREOFFICE_PATH"),
        os.environ.get("LIBREOFFICE_HOME"),
    ]

    candidate_paths: list[Path] = []

    executable_names = ["soffice", "libreoffice"]
    if os.name == "nt":
        executable_names.extend(["soffice.exe", "libreoffice.exe"])

    for executable_name in executable_names:
        resolved = shutil.which(executable_name)
        if resolved:
            candidate_paths.append(Path(resolved))

    for env_value in env_candidates:
        if not env_value:
            continue
        env_path = Path(env_value)
        if env_path.is_file():
            candidate_paths.append(env_path)
        elif env_path.is_dir():
            candidate_paths.extend(
                [
                    env_path / "soffice",
                    env_path / "libreoffice",
                ]
            )
            candidate_paths.extend(
                [
                    env_path / "soffice.exe",
                    env_path / "libreoffice.exe",
                    env_path / "program" / "soffice.exe",
                    env_path / "program" / "libreoffice.exe",
                    env_path / "program" / "soffice",
                    env_path / "program" / "libreoffice",
                ]
            )

    if os.name == "nt":
        windows_roots = [
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("LOCALAPPDATA"),
        ]
        for root in windows_roots:
            if not root:
                continue
            root_path = Path(root)
            candidate_paths.extend(
                [
                    root_path / "LibreOffice" / "program" / "soffice",
                    root_path / "LibreOffice" / "program" / "libreoffice",
                    root_path / "LibreOffice" / "program" / "soffice.exe",
                    root_path / "LibreOffice" / "program" / "libreoffice.exe",
                    root_path / "Programs" / "LibreOffice" / "program" / "soffice.exe",
                ]
            )

    for candidate in candidate_paths:
        if candidate.exists():
            return str(candidate), warnings

    warnings.append("未找到 LibreOffice/soffice，无法完成 DOCX→PDF 基础转换。")
    return None, warnings


def _convert_docx_to_pdf(
    source_docx: Path, output_dir: Path
) -> tuple[Path | None, list[str]]:
    warnings: list[str] = []
    if not source_docx.exists() or source_docx.suffix.lower() != ".docx":
        warnings.append("PDF 基础转换跳过：源文件不是 .docx 或文件不存在。")
        return None, warnings

    output_dir.mkdir(parents=True, exist_ok=True)

    converter, resolution_warnings = _resolve_libreoffice_converter()
    warnings.extend(resolution_warnings)
    if not converter:
        return None, warnings

    try:
        subprocess.run(
            [
                converter,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output_dir),
                str(source_docx),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        error_details = "; ".join(
            part.strip()
            for part in [exc.stdout or "", exc.stderr or ""]
            if part and part.strip()
        )
        if error_details:
            warnings.append(
                f"{converter} 转换失败：{error_details}，已回退到重建式 PDF 渲染。"
            )
        else:
            warnings.append(
                f"{converter} 转换失败，退出码 {exc.returncode}，已回退到重建式 PDF 渲染。"
            )
        return None, warnings
    except Exception as exc:
        warnings.append(f"{converter} 转换失败：{exc}，已回退到重建式 PDF 渲染。")
        return None, warnings

    candidate = output_dir / f"{source_docx.stem}.pdf"
    if candidate.exists():
        if _pdf_has_meaningful_content(candidate):
            return candidate, warnings
        warnings.append(
            f"{candidate.name} 生成后内容几乎为空，已回退到重建式 PDF 渲染。"
        )
        return None, warnings

    warnings.append("转换完成但未找到基础 PDF 输出文件，已回退到重建式 PDF 渲染。")
    return None, warnings


def _page_issue_entry(
    text: str,
    *,
    y: float,
    severity: float,
    kind: str,
    source: str,
    rect: Any | None = None,
    page_number: int | None = None,
) -> dict[str, Any]:
    return {
        "text": text,
        "y": y,
        "severity": severity,
        "kind": kind,
        "source": source,
        "rect": rect,
        "page_number": page_number,
    }


def _annotate_pdf_from_report(doc: Any, report_payload: dict[str, Any]) -> None:
    import fitz

    parsed_data = _extract_parsed_data(report_payload)
    sections = _extract_sections(parsed_data)
    section_index = _build_section_index(sections)
    section_page_map = _build_pdf_section_page_map(doc, sections)
    ai_review = (
        report_payload.get("ai_review")
        if isinstance(report_payload.get("ai_review"), dict)
        else {}
    )
    reference_verification = (
        report_payload.get("reference_verification")
        if isinstance(report_payload.get("reference_verification"), list)
        else []
    )

    page_issues: dict[int, list[dict[str, Any]]] = defaultdict(list)

    def _safe_page(page_number: int):
        index = page_number - 1
        if index < 0 or index >= len(doc):
            return None
        return doc[index]

    def _safe_note_point(rect: Any) -> Any:
        return fitz.Point(min(rect.x1 + 8.0, rect.x0 + 160.0), max(rect.y0 - 10.0, 6.0))

    for chunk_review in ai_review.get("chunk_reviews", []):
        if not isinstance(chunk_review, dict):
            continue
        section_id = chunk_review.get("section_id")
        if not isinstance(section_id, int):
            continue
        section = section_index.get(section_id)
        if not section:
            continue
        coordinates = _section_coordinates(section)
        if not coordinates:
            continue

        page_number = section_page_map.get(section_id, coordinates["page"])
        issue_list = chunk_review.get("issues", [])
        if not isinstance(issue_list, list):
            continue

        matched_location = _find_section_rect_on_pdf(doc, section, page_number)
        if matched_location is not None:
            page_number, rect = matched_location
        else:
            rect = fitz.Rect(
                coordinates["x"],
                coordinates["y"],
                coordinates["x"] + coordinates["width"],
                coordinates["y"] + coordinates["height"],
            )

        page = _safe_page(page_number)
        if page is None:
            continue

        for issue in issue_list:
            if not isinstance(issue, dict):
                continue
            note_text = _format_issue_note(section_id, issue)
            page_issues[page_number].append(
                _page_issue_entry(
                    note_text,
                    y=coordinates["y"],
                    severity=max(_issue_severity_score(issue), 2.0),
                    kind=str(issue.get("issue_type") or "issue"),
                    source="chunk_review",
                    rect=rect,
                    page_number=page_number,
                )
            )

    for index, verification in enumerate(reference_verification, start=1):
        if not isinstance(verification, dict):
            continue
        reference = (
            verification.get("reference")
            if isinstance(verification.get("reference"), dict)
            else {}
        )
        reference_text = str(
            reference.get("text") or reference.get("raw_text") or ""
        ).strip()
        matched_section = _reference_section_for_text(reference_text, sections)
        if matched_section:
            coordinates = _section_coordinates(matched_section)
            if not coordinates:
                continue
            section_id = matched_section.get("id")
            page_number = (
                section_page_map.get(section_id, coordinates["page"])
                if isinstance(section_id, int)
                else coordinates["page"]
            )
            matched_location = (
                _find_section_rect_on_pdf(doc, matched_section, page_number)
                if isinstance(section_id, int)
                else None
            )
            if matched_location is not None:
                page_number, anchor_rect = matched_location
            else:
                anchor_rect = fitz.Rect(
                    coordinates["x"],
                    coordinates["y"],
                    coordinates["x"] + coordinates["width"],
                    coordinates["y"] + coordinates["height"],
                )
            page = _safe_page(page_number)
            if page is None:
                continue
        else:
            page = _safe_page(1)
            if page is None:
                continue
            anchor_rect = fitz.Rect(24.0, 24.0, 220.0, 60.0)
            page_number = 1

        note_text = _format_reference_note(index, verification)
        page_issues[page_number].append(
            _page_issue_entry(
                note_text,
                y=anchor_rect.y0,
                severity=_issue_severity_score({"severity": "low"}),
                kind="reference",
                source="reference_verification",
                rect=anchor_rect,
                page_number=page_number,
            )
        )

    for page_number, issues in page_issues.items():
        page = _safe_page(page_number)
        if page is None:
            continue

        page_rect = page.rect
        layout = _calculate_annotation_layout(issues, page_rect.height, page_rect.width)
        visible_issues = layout.get("visible_issues", issues)

        for index, issue in enumerate(visible_issues):
            rect = issue.get("rect")
            if rect is None:
                continue
            try:
                highlight = page.add_highlight_annot(rect)
                highlight.update()
            except Exception:
                pass
            try:
                note_point = fitz.Point(
                    min(rect.x1 + 8.0, page_rect.width - 12.0),
                    max(rect.y0 - 10.0 + index * 18.0, 6.0),
                )
                text_annot = page.add_text_annot(
                    note_point, str(issue.get("text") or "")
                )
                text_annot.set_info(content=str(issue.get("text") or ""))
                text_annot.update()
            except Exception:
                pass

        overflow_count = int(layout.get("overflow_count") or 0)
        if overflow_count > 0:
            summary_text = _format_overflow_note(overflow_count)
            summary_point = fitz.Point(page_rect.width - 72.0, 24.0)
            try:
                summary_annot = page.add_text_annot(summary_point, summary_text)
                summary_annot.set_info(content=summary_text)
                summary_annot.update()
            except Exception:
                pass


def _render_pdf_annotation_report(
    report_payload: dict[str, Any], pdf_path: Path
) -> list[str]:
    import fitz

    generation_warnings: list[str] = []
    source_docx_candidates: list[Path] = []
    for key in ("annotated_path", "source_file", "file_path"):
        value = report_payload.get(key)
        if isinstance(value, str) and value.strip():
            candidate = Path(value)
            if (
                candidate.suffix.lower() == ".docx"
                and candidate not in source_docx_candidates
            ):
                source_docx_candidates.append(candidate)

    for source_docx in source_docx_candidates:
        if not source_docx.exists():
            continue
        with tempfile.TemporaryDirectory(prefix="paper_audit_pdf_") as scratch_dir:
            converted_pdf, conversion_warnings = _convert_docx_to_pdf(
                source_docx, Path(scratch_dir)
            )
            generation_warnings.extend(conversion_warnings)
            if converted_pdf and converted_pdf.exists():
                try:
                    doc = fitz.open(str(converted_pdf))
                    try:
                        _annotate_pdf_from_report(doc, report_payload)
                        doc.save(str(pdf_path))
                        return generation_warnings
                    finally:
                        doc.close()
                except Exception:
                    generation_warnings.append(
                        "基础 PDF 已生成，但叠加批注失败，已回退到重建式 PDF 渲染。"
                    )
                    break

    if source_docx_candidates:
        generation_warnings.append(
            "未找到可用的 DOCX 源文件，已回退到重建式 PDF 渲染。"
        )

    parsed_data = _extract_parsed_data(report_payload)
    sections = _extract_sections(parsed_data)
    section_index = _build_section_index(sections)
    ai_review = (
        report_payload.get("ai_review")
        if isinstance(report_payload.get("ai_review"), dict)
        else {}
    )
    reference_verification = (
        report_payload.get("reference_verification")
        if isinstance(report_payload.get("reference_verification"), list)
        else []
    )

    font_manager = _FONT_MANAGER
    default_font_size = 12.0
    annotation_font_size = 16.0

    notes_by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for chunk_review in ai_review.get("chunk_reviews", []):
        if not isinstance(chunk_review, dict):
            continue
        section_id = chunk_review.get("section_id")
        if not isinstance(section_id, int):
            continue
        section = section_index.get(section_id)
        if not section:
            continue
        coordinates = _section_coordinates(section)
        if not coordinates:
            continue
        issue_list = chunk_review.get("issues", [])
        if not isinstance(issue_list, list):
            continue
        for issue in issue_list:
            if not isinstance(issue, dict):
                continue
            note_text = _format_issue_note(section_id, issue)
            notes_by_page[coordinates["page"]].append(
                {
                    "y": coordinates["y"],
                    "text": note_text,
                    "font_size": annotation_font_size,
                    "severity": max(_issue_severity_score(issue), 2.0),
                    "kind": str(issue.get("issue_type") or "issue"),
                }
            )

    for index, verification in enumerate(reference_verification, start=1):
        if not isinstance(verification, dict):
            continue
        reference = (
            verification.get("reference")
            if isinstance(verification.get("reference"), dict)
            else {}
        )
        reference_text = str(
            reference.get("text") or reference.get("raw_text") or ""
        ).strip()
        matched_section = _reference_section_for_text(reference_text, sections)
        if matched_section:
            coordinates = _section_coordinates(matched_section)
            page_number = coordinates["page"] if coordinates else 1
            anchor_y = coordinates["y"] if coordinates else 24.0
        else:
            page_number = 1
            anchor_y = 24.0
        notes_by_page[page_number].append(
            {
                "y": anchor_y,
                "text": _format_reference_note(index, verification),
                "font_size": annotation_font_size,
                "severity": 1.0,
                "kind": "reference",
            }
        )

    page_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    page_bounds: dict[int, dict[str, float]] = defaultdict(
        lambda: {"max_right": 0.0, "max_bottom": 0.0}
    )

    for section in sections:
        coordinates = _section_coordinates(section)
        if not coordinates:
            continue
        page_groups[coordinates["page"]].append(section)
        bounds = page_bounds[coordinates["page"]]
        bounds["max_right"] = max(
            bounds["max_right"], coordinates["x"] + coordinates["width"]
        )
        bounds["max_bottom"] = max(
            bounds["max_bottom"], coordinates["y"] + coordinates["height"]
        )

    if not page_groups:
        page_groups[1] = sections

    doc = fitz.open()

    def draw_text(
        page: Any,
        box: fitz.Rect,
        text: str,
        *,
        font_size: float,
        font_name: str,
        color: tuple[float, float, float],
    ) -> None:
        effective_font_name, effective_fontfile = font_manager.resolve(font_name, text)
        if not effective_fontfile:
            effective_font_name = "helv"
        page.insert_textbox(
            box,
            text,
            fontsize=font_size,
            fontname=effective_font_name,
            fontfile=effective_fontfile,
            color=color,
            overlay=True,
            align=fitz.TEXT_ALIGN_LEFT,
        )

    if any(_section_coordinates(section) for section in sections):
        page_numbers = sorted(set(page_groups) | set(notes_by_page))
        for page_number in page_numbers:
            page_sections = page_groups.get(page_number, [])
            page_notes = notes_by_page.get(page_number, [])
            bounds = page_bounds.get(
                page_number, {"max_right": 450.0, "max_bottom": 720.0}
            )
            page_width, page_height, sidebar_x, page_margin = _estimate_page_size(
                bounds["max_right"],
                bounds["max_bottom"],
                len(page_notes),
            )
            page = doc.new_page(width=page_width, height=page_height)
            layout = _calculate_annotation_layout(page_notes, page_height, page_width)
            visible_notes = layout.get("visible_issues", page_notes)
            sidebar_width = float(layout.get("sidebar_width") or 220.0)
            sidebar_x = max(page_width - sidebar_width - page_margin, sidebar_x)

            for section in page_sections:
                coordinates = _section_coordinates(section)
                if not coordinates:
                    continue
                raw_text = str(section.get("raw_text") or section.get("text") or "")
                if not raw_text.strip():
                    continue
                formatting = (
                    section.get("formatting")
                    if isinstance(section.get("formatting"), dict)
                    else {}
                )
                font_size = _parse_font_size(formatting.get("size"), default_font_size)
                font_name = "simsun"
                section_font = str(formatting.get("font") or "").strip()
                if "黑体" in section_font:
                    font_name = "simhei"
                box = fitz.Rect(
                    coordinates["x"] + page_margin,
                    coordinates["y"] + page_margin,
                    coordinates["x"] + coordinates["width"] + page_margin,
                    coordinates["y"]
                    + max(coordinates["height"], font_size * 1.5)
                    + page_margin,
                )
                draw_text(
                    page,
                    box,
                    raw_text,
                    font_size=font_size,
                    font_name=font_name,
                    color=(0, 0, 0),
                )

            note_y = page_margin
            for note in visible_notes:
                note_y = max(note_y, float(note.get("y", 0.0)) + page_margin)
                note_box = fitz.Rect(
                    sidebar_x,
                    note_y,
                    page_width - page_margin,
                    note_y + 36.0,
                )
                draw_text(
                    page,
                    note_box,
                    str(note.get("text") or ""),
                    font_size=float(note.get("font_size") or annotation_font_size),
                    font_name="simsun",
                    color=(1, 0, 0),
                )
                note_y += 42.0

            overflow_count = int(layout.get("overflow_count") or 0)
            if overflow_count > 0:
                note_box = fitz.Rect(
                    sidebar_x,
                    page_margin,
                    page_width - page_margin,
                    page_margin + 56.0,
                )
                draw_text(
                    page,
                    note_box,
                    _format_overflow_note(overflow_count),
                    font_size=11.0,
                    font_name="simsun",
                    color=(0.8, 0.2, 0.2),
                )
    else:
        page_width = 780.0
        page_height = max(
            842.0, 240.0 + len(sections) * 32.0 + len(notes_by_page.get(1, [])) * 42.0
        )
        page = doc.new_page(width=page_width, height=page_height)
        page_margin = 24.0
        y_cursor = page_margin
        layout = _calculate_annotation_layout(
            notes_by_page.get(1, []), page_height, page_width
        )
        visible_notes = layout.get("visible_issues", notes_by_page.get(1, []))
        sidebar_width = float(layout.get("sidebar_width") or 220.0)
        sidebar_x = max(page_width - sidebar_width - page_margin, 420.0)

        for section in sections:
            raw_text = str(section.get("raw_text") or section.get("text") or "")
            if not raw_text.strip():
                continue
            font_size = _parse_font_size(
                (
                    section.get("formatting", {}).get("size")
                    if isinstance(section.get("formatting"), dict)
                    else None
                ),
                default_font_size,
            )
            note_box = fitz.Rect(
                page_margin, y_cursor, sidebar_x - 16.0, y_cursor + font_size * 2
            )
            draw_text(
                page,
                note_box,
                raw_text,
                font_size=font_size,
                font_name="simsun",
                color=(0, 0, 0),
            )
            y_cursor += max(font_size * 1.8, 28.0)

        note_y = page_margin
        for note in visible_notes:
            note_box = fitz.Rect(
                sidebar_x, note_y, page_width - page_margin, note_y + 36.0
            )
            draw_text(
                page,
                note_box,
                str(note.get("text") or ""),
                font_size=float(note.get("font_size") or annotation_font_size),
                font_name="simsun",
                color=(1, 0, 0),
            )
            note_y += 42.0

        overflow_count = int(layout.get("overflow_count") or 0)
        if overflow_count > 0:
            note_box = fitz.Rect(
                sidebar_x,
                page_margin,
                page_width - page_margin,
                page_margin + 56.0,
            )
            draw_text(
                page,
                note_box,
                _format_overflow_note(overflow_count),
                font_size=11.0,
                font_name="simsun",
                color=(0.8, 0.2, 0.2),
            )

    doc.save(str(pdf_path))
    doc.close()
    if generation_warnings:
        generation_warnings.append("当前 PDF 使用重建式渲染作为回退方案。")
    return generation_warnings


async def _process_task(task_id: int, file_path: str, *, resume: bool = False) -> None:
    async with _task_semaphore:
        tq = TaskQueue(str(settings.SQLITE_DB_PATH))
        await tq.init_db()

        absolute_file_path = str(Path(file_path).resolve())

        output_dir = settings.PYTHON_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"report_{task_id}.json"
        task_row = await tq.get_task(task_id)
        checkpoint = (
            _decode_checkpoint(TaskQueue.row_to_dict(task_row) if task_row else None)
            if resume
            else {}
        )

        try:
            await tq.update_task(
                task_id,
                status="processing",
                progress=10,
                current_stage=checkpoint.get("stage", "parsing"),
            )

            parse_result = checkpoint.get("parse_result")
            parsed_data = checkpoint.get("parsed_data")
            if not isinstance(parse_result, dict) or not isinstance(parsed_data, dict):
                parse_result = await rust_client.parse(absolute_file_path)
                parsed_data = parse_result.get("data", parse_result)
                checkpoint = {
                    "stage": "parsed",
                    "source_file": absolute_file_path,
                    "parse_result": parse_result,
                    "parsed_data": parsed_data,
                }
                await _save_checkpoint(
                    tq, task_id, checkpoint, current_stage="parsing", progress=25
                )
            else:
                checkpoint.setdefault("stage", "parsed")
                checkpoint.setdefault("source_file", absolute_file_path)
                await tq.update_task(task_id, current_stage="parsing", progress=25)

            await tq.update_task(task_id, progress=35, current_stage="analyzing")

            # Run AI review workflow (chunk review + reference verification)
            from ..core.langgraph import review_document

            ai_review = checkpoint.get("ai_review")
            if not isinstance(ai_review, dict):
                await tq.update_task(task_id, progress=55, current_stage="ai_review")
                ai_review = await review_document(parsed_data)
                checkpoint.update(
                    {
                        "stage": "reviewed",
                        "ai_review": ai_review,
                    }
                )
                await _save_checkpoint(
                    tq, task_id, checkpoint, current_stage="ai_review", progress=55
                )
            else:
                await tq.update_task(task_id, progress=55, current_stage="ai_review")

            chunks = ai_review.get("chunks", [])
            chunk_reviews = ai_review.get("chunk_reviews", [])
            reference_results = ai_review.get("reference_verification", [])
            consistency_issues = ai_review.get("consistency_issues", [])
            await tq.update_task(task_id, progress=75, current_stage="reporting")

            report_payload = {
                "task_id": task_id,
                "source_file": absolute_file_path,
                "parse_result": parse_result,
                "chunks": chunks,
                "ai_review": ai_review,
                "reference_verification": reference_results,
                "chunk_reviews": chunk_reviews,
                "issues_count": sum(
                    item.get("issue_count", 0) for item in chunk_reviews
                )
                + sum(
                    1
                    for item in reference_results
                    if item.get("verdict") not in {"verified", None, ""}
                )
                + len(consistency_issues),
            }

            report_payload_for_json = dict(report_payload)
            report_payload_for_json["ai_review"] = _compact_ai_review_for_report(
                ai_review
            )
            report_payload_for_json["chunk_reviews"] = report_payload_for_json[
                "ai_review"
            ].get("chunk_reviews", chunk_reviews)

            report_path.write_text(
                json.dumps(report_payload_for_json, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            checkpoint.update(
                {
                    "stage": "reported",
                    "report_path": str(report_path),
                }
            )
            await _save_checkpoint(
                tq, task_id, checkpoint, current_stage="reporting", progress=90
            )
            await tq.update_task(
                task_id,
                status="done",
                progress=100,
                result_path=str(report_path),
                current_stage="completed",
                error_message=None,
                checkpoint_data=json.dumps(checkpoint, ensure_ascii=False),
            )
        except Exception as exc:
            await tq.update_task(
                task_id,
                status="failed",
                progress=100,
                current_stage="failed",
                error_message=str(exc),
                error_log=str(exc),
                checkpoint_data=(
                    json.dumps(checkpoint, ensure_ascii=False) if checkpoint else None
                ),
            )


async def resume_recoverable_tasks() -> int:
    tq = TaskQueue(str(settings.SQLITE_DB_PATH))
    await tq.init_db()
    rows = await tq.list_resumable_tasks()
    resumed = 0
    for row in rows:
        task = TaskQueue.row_to_dict(row)
        if not task:
            continue
        task_id = int(task["id"])
        file_path = str(task["file_path"])
        current_stage = str(task.get("current_stage") or "")
        if task.get("status") == "done" or current_stage == "completed":
            continue
        asyncio.create_task(_process_task(task_id, file_path, resume=True))
        resumed += 1
    return resumed


@router.post("/api/v1/tasks/{task_id}/resume")
async def resume_task(task_id: int):
    tq = TaskQueue(str(settings.SQLITE_DB_PATH))
    await tq.init_db()
    row = await tq.get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="task not found")
    task = TaskQueue.row_to_dict(row)
    checkpoint = _decode_checkpoint(task)
    if not checkpoint:
        raise HTTPException(status_code=409, detail="checkpoint not available")
    if task.get("status") == "processing":
        raise HTTPException(status_code=409, detail="task already processing")
    asyncio.create_task(_process_task(task_id, str(task["file_path"]), resume=True))
    return {
        "task_id": task_id,
        "status": "resuming",
        "checkpoint_stage": checkpoint.get("stage"),
    }


@router.post("/api/v1/audit", status_code=202)
async def create_audit(
    file: UploadFile = File(...),
    audit_config: str | None = Form(None),
):
    upload_dir: Path = settings.PYTHON_UPLOAD_DIR
    upload_dir.mkdir(parents=True, exist_ok=True)
    if file.content_type not in {
        None,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    }:
        raise HTTPException(status_code=400, detail="unsupported file type")

    config = {}
    if audit_config:
        try:
            config = json.loads(audit_config)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="invalid audit_config")

    max_mb = int(config.get("max_file_size_mb", settings.MAX_FILE_SIZE_MB))
    content = await file.read()
    if len(content) > max_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="file too large")

    # Save uploaded file using a UUID-prefixed filename to avoid overwriting
    safe_name = Path(file.filename).name
    dest = (upload_dir / f"{uuid4().hex}_{safe_name}").resolve()
    dest.write_bytes(content)

    tq = TaskQueue(str(settings.SQLITE_DB_PATH))
    await tq.init_db()
    task_id = await tq.create_task(str(dest))
    asyncio.create_task(_process_task(task_id, str(dest)))
    return {"task_id": task_id, "status": "pending"}
