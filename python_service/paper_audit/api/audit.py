from __future__ import annotations

import asyncio
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from uuid import uuid4

from ..config import settings
from ..core import rust_client
from ..core.task_queue import TaskQueue

router = APIRouter()
_task_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_TASKS)


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


def _resolve_cjk_font_file(font_name: str | None = None) -> str | None:
    font_candidates: list[Path]
    if font_name and "黑体" in font_name:
        font_candidates = [
            Path(r"C:\Windows\Fonts\simhei.ttf"),
            Path(r"C:\Windows\Fonts\simsun.ttc"),
            Path(r"C:\Windows\Fonts\simsun.ttf"),
        ]
    else:
        font_candidates = [
            Path(r"C:\Windows\Fonts\simsun.ttc"),
            Path(r"C:\Windows\Fonts\simsun.ttf"),
            Path(r"C:\Windows\Fonts\simhei.ttf"),
        ]

    for candidate in font_candidates:
        if candidate.exists():
            return str(candidate)
    return None


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


def _render_pdf_annotation_report(
    report_payload: dict[str, Any], pdf_path: Path
) -> None:
    import fitz

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

    font_file = _resolve_cjk_font_file("宋体")
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
        page.insert_textbox(
            box,
            text,
            fontsize=font_size,
            fontname=font_name,
            fontfile=font_file,
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
            for note in sorted(page_notes, key=lambda item: float(item.get("y", 0.0))):
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
    else:
        page_width = 780.0
        page_height = max(
            842.0, 240.0 + len(sections) * 32.0 + len(notes_by_page.get(1, [])) * 42.0
        )
        page = doc.new_page(width=page_width, height=page_height)
        page_margin = 24.0
        sidebar_x = 420.0
        y_cursor = page_margin

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
        for note in notes_by_page.get(1, []):
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

    doc.save(str(pdf_path))
    doc.close()


async def _process_task(task_id: int, file_path: str, *, resume: bool = False) -> None:
    async with _task_semaphore:
        tq = TaskQueue(str(settings.SQLITE_DB_PATH))
        await tq.init_db()

        absolute_file_path = str(Path(file_path).resolve())

        output_dir = settings.PYTHON_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"report_{task_id}.json"
        zip_path = output_dir / f"task_{task_id}.zip"
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
            await tq.update_task(task_id, progress=75, current_stage="annotating")

            issues = parsed_data.get("sections", [])
            annotate_result = await rust_client.annotate(
                absolute_file_path,
                issues,
                output_filename=f"{task_id}_annotated.docx",
            )
            annotated_path = annotate_result.get("output_path")

            report_payload = {
                "task_id": task_id,
                "source_file": absolute_file_path,
                "parse_result": parse_result,
                "chunks": chunks,
                "ai_review": ai_review,
                "reference_verification": reference_results,
                "chunk_reviews": chunk_reviews,
                "annotated_path": annotated_path,
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

            checkpoint.update(
                {
                    "stage": "annotated",
                    "annotated_path": annotated_path,
                    "report_path": str(report_path),
                    "zip_path": str(zip_path),
                }
            )
            await _save_checkpoint(
                tq, task_id, checkpoint, current_stage="annotating", progress=90
            )

            should_write_report_json = report_payload["issues_count"] > 0
            if should_write_report_json:
                report_path.write_text(
                    json.dumps(report_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            elif report_path.exists():
                report_path.unlink()

            try:
                pdf_path = output_dir / f"report_{task_id}.pdf"
                _render_pdf_annotation_report(report_payload, pdf_path)
            except Exception:
                pdf_path = None

            with zipfile.ZipFile(
                zip_path, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                if annotated_path and Path(annotated_path).exists():
                    archive.write(annotated_path, arcname=Path(annotated_path).name)
                if report_path.exists():
                    archive.write(report_path, arcname=report_path.name)
                if pdf_path and Path(pdf_path).exists():
                    archive.write(pdf_path, arcname=Path(pdf_path).name)

            # Remove temporary Rust parse JSON if present
            try:
                temp_path = None
                if isinstance(parse_result, dict):
                    temp_path = parse_result.get("temp_output_path")
                if temp_path:
                    t = Path(str(temp_path))
                    if t.exists():
                        t.unlink()
            except Exception:
                pass

            await tq.update_task(
                task_id,
                status="done",
                progress=100,
                result_path=str(zip_path),
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
