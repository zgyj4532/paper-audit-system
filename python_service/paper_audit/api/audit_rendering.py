from __future__ import annotations

import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from .audit_common import (
    _FONT_MANAGER,
    _build_section_index,
    _build_pdf_section_page_map,
    _calculate_annotation_layout,
    _convert_docx_to_pdf,
    _estimate_page_size,
    _extract_parsed_data,
    _extract_sections,
    _find_section_rect_on_pdf,
    _format_issue_note,
    _format_overflow_note,
    _format_reference_note,
    _issue_severity_score,
    _parse_font_size,
    _reference_section_for_text,
    _section_coordinates,
)


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
                {
                    "text": note_text,
                    "y": coordinates["y"],
                    "severity": max(_issue_severity_score(issue), 2.0),
                    "kind": str(issue.get("issue_type") or "issue"),
                    "source": "chunk_review",
                    "rect": rect,
                    "page_number": page_number,
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
            {
                "text": note_text,
                "y": anchor_rect.y0,
                "severity": _issue_severity_score({"severity": "low"}),
                "kind": "reference",
                "source": "reference_verification",
                "rect": anchor_rect,
                "page_number": page_number,
            }
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
                bounds["max_right"], bounds["max_bottom"], len(page_notes)
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
                    sidebar_x, page_margin, page_width - page_margin, page_margin + 56.0
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
                sidebar_x, page_margin, page_width - page_margin, page_margin + 56.0
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
