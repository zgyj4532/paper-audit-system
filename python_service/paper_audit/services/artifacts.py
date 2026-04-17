from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from ..config import settings


def _output_dir(base_dir: Path | None = None) -> Path:
    return base_dir if base_dir is not None else settings.PYTHON_OUTPUT_DIR


def _report_json_path(task_id: int, output_dir: Path) -> Path:
    return output_dir / f"report_{task_id}.json"


def _load_json_payload(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _first_existing(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _candidate_docx_paths(
    task: dict[str, Any],
    task_id: int,
    output_dir: Path,
    report_payload: dict[str, Any] | None,
) -> list[Path]:
    candidates: list[Path] = []

    if isinstance(report_payload, dict):
        annotated_path = report_payload.get("annotated_path")
        if isinstance(annotated_path, str) and annotated_path.strip():
            candidates.append(Path(annotated_path))

    result_path = task.get("result_path")
    if isinstance(result_path, str) and result_path.strip():
        result_file = Path(result_path)
        if result_file.suffix.lower() == ".docx":
            candidates.append(result_file)

    file_path = task.get("file_path")
    if isinstance(file_path, str) and file_path.strip():
        candidates.append(Path(file_path))

    candidates.extend(
        [
            output_dir / f"{task_id}_annotated.docx",
            output_dir / f"report_{task_id}_annotated.docx",
        ]
    )

    return candidates


def _ensure_pdf_from_report(
    task_id: int,
    output_dir: Path,
    report_payload: dict[str, Any],
) -> tuple[Path | None, list[str]]:
    from ..api.audit import _render_pdf_annotation_report

    pdf_path = output_dir / f"report_{task_id}.pdf"
    warnings = _render_pdf_annotation_report(report_payload, pdf_path)
    if pdf_path.exists():
        return pdf_path, warnings
    return None, warnings


def ensure_task_zip_artifact(
    task_id: int,
    task: dict[str, Any],
    output_dir: Path | None = None,
) -> tuple[Path | None, list[str]]:
    resolved_output_dir = _output_dir(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    result_path = task.get("result_path")
    if isinstance(result_path, str) and result_path.strip():
        result_file = Path(result_path)
        if result_file.exists() and zipfile.is_zipfile(result_file):
            return result_file, warnings

    report_json_path = _report_json_path(task_id, resolved_output_dir)
    report_payload = _load_json_payload(report_json_path)
    if report_payload is None:
        warnings.append("报告 JSON 不存在，无法恢复结果压缩包。")
        return None, warnings

    docx_path = _first_existing(
        _candidate_docx_paths(task, task_id, resolved_output_dir, report_payload)
    )

    pdf_path = resolved_output_dir / f"report_{task_id}.pdf"
    if not pdf_path.exists():
        pdf_path, pdf_warnings = _ensure_pdf_from_report(
            task_id, resolved_output_dir, report_payload
        )
        warnings.extend(pdf_warnings)

    zip_path = resolved_output_dir / f"task_{task_id}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if docx_path and docx_path.exists():
            archive.write(docx_path, arcname=f"{task_id}_annotated.docx")
        archive.writestr(
            report_json_path.name,
            json.dumps(report_payload, ensure_ascii=False, indent=2),
        )
        if pdf_path and pdf_path.exists():
            archive.write(pdf_path, arcname=pdf_path.name)

    warnings.append("结果压缩包已从现有报告数据恢复。")
    return zip_path, warnings


def ensure_task_pdf_artifact(
    task_id: int,
    task: dict[str, Any],
    output_dir: Path | None = None,
) -> tuple[Path | None, list[str]]:
    resolved_output_dir = _output_dir(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    pdf_path = resolved_output_dir / f"report_{task_id}.pdf"
    if pdf_path.exists() and pdf_path.is_file():
        return pdf_path, warnings

    report_json_path = _report_json_path(task_id, resolved_output_dir)
    report_payload = _load_json_payload(report_json_path)
    if report_payload is None:
        warnings.append("报告 JSON 不存在，无法恢复 PDF。")
        return None, warnings

    pdf_path, pdf_warnings = _ensure_pdf_from_report(
        task_id, resolved_output_dir, report_payload
    )
    warnings.extend(pdf_warnings)
    return pdf_path, warnings


def ensure_task_docx_artifact(
    task_id: int,
    task: dict[str, Any],
    output_dir: Path | None = None,
) -> tuple[Path | None, list[str]]:
    resolved_output_dir = _output_dir(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    result_path = task.get("result_path")
    if isinstance(result_path, str) and result_path.strip():
        result_file = Path(result_path)
        if result_file.exists():
            if result_file.suffix.lower() == ".docx":
                return result_file, warnings
            if zipfile.is_zipfile(result_file):
                with zipfile.ZipFile(result_file, "r") as archive:
                    docx_name = next(
                        (
                            name
                            for name in archive.namelist()
                            if name.endswith("_annotated.docx")
                        ),
                        None,
                    )
                    if docx_name:
                        extracted = (
                            resolved_output_dir / Path(docx_name).name
                        )
                        extracted.write_bytes(archive.read(docx_name))
                        return extracted, warnings

    report_json_path = _report_json_path(task_id, resolved_output_dir)
    report_payload = _load_json_payload(report_json_path)
    docx_path = _first_existing(
        _candidate_docx_paths(task, task_id, resolved_output_dir, report_payload)
    )
    if docx_path is not None:
        return docx_path, warnings

    warnings.append("未能定位可下载的 DOCX。")
    return None, warnings