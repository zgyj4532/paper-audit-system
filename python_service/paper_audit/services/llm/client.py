from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence

import httpx

from ...config import settings
from .audit_prompt import build_review_request
from .table_prompt import build_table_validation_request
from .verify_prompt import build_reference_request


def normalize_dashscope_base_url(base_url: str) -> str:
    cleaned = base_url.rstrip("/")
    if cleaned.endswith("/api/v1"):
        return cleaned[: -len("/api/v1")]
    return cleaned


def _extract_choice_content(payload: Dict[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            message = (
                first_choice.get("message") or first_choice.get("delta") or first_choice
            )
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content

    output = payload.get("output")
    if isinstance(output, dict):
        text = output.get("text")
        if isinstance(text, str) and text.strip():
            return text
        choices = output.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                message = first_choice.get("message") or first_choice
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        return content

    raise ValueError("Qwen response did not contain assistant content")


def _extract_json(content: str) -> Dict[str, Any]:
    text = content.strip()
    if not text:
        return {"raw": ""}

    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            pass

    return {"raw": text}


@dataclass(slots=True)
class QwenClient:
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    timeout: float = 45.0

    def __post_init__(self) -> None:
        self.api_key = self.api_key or settings.QWEN_API_KEY
        self.base_url = self.base_url or settings.QWEN_BASE_URL
        self.model = self.model or settings.QWEN_MODEL
        if not self.api_key:
            raise RuntimeError("QWEN_API_KEY is not configured")

    @property
    def _candidate_urls(self) -> List[str]:
        base_url = self.base_url.rstrip("/")
        service_root = normalize_dashscope_base_url(base_url)
        candidates = [
            f"{service_root}/compatible-mode/v1/chat/completions",
            f"{base_url}/chat/completions",
        ]
        deduped: List[str] = []
        for url in candidates:
            if url not in deduped:
                deduped.append(url)
        return deduped

    async def chat(
        self,
        prompt: str | None = None,
        *,
        messages: Sequence[Dict[str, Any]] | None = None,
        max_tokens: int = 256,
        temperature: float = 0.0,
        response_format: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if messages is None:
            if prompt is None:
                raise ValueError("prompt or messages must be provided")
            messages = [{"role": "user", "content": prompt}]

        payload = {
            "model": self.model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format
        headers = {"Authorization": f"Bearer {self.api_key}"}

        last_error: Exception | None = None
        attempt_errors: List[str] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for api_url in self._candidate_urls:
                try:
                    response = await client.post(api_url, json=payload, headers=headers)
                    response.raise_for_status()
                    response_data = response.json()
                    content = _extract_choice_content(response_data)
                    return {
                        "ok": True,
                        "api_url": api_url,
                        "raw": response_data,
                        "content": content,
                        "json": _extract_json(content),
                    }
                except Exception as exc:
                    last_error = exc
                    attempt_errors.append(f"{api_url}: {exc}")

        error_detail = " | ".join(attempt_errors) if attempt_errors else str(last_error)
        raise RuntimeError(
            f"Qwen request failed after trying {len(self._candidate_urls)} endpoint(s): {error_detail}"
        )

    async def ping(self) -> Dict[str, Any]:
        result = await self.chat(
            '请只回复一个 JSON: {"ok": true, "message": "pong"}',
            max_tokens=32,
            response_format={"type": "json_object"},
        )
        return {
            "ok": True,
            "message": result["json"].get("message", "pong"),
            "backend": "qwen",
            "raw": result["json"],
        }

    async def review_chunk(
        self,
        text: str,
        *,
        section_id: Any = None,
        strictness: int = 3,
        focus_areas: Iterable[str] | None = None,
    ) -> Dict[str, Any]:
        request = build_review_request(
            text, section_id=section_id, strictness=strictness, focus_areas=focus_areas
        )
        result = await self.chat(
            messages=request.messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            response_format=request.response_format,
        )
        issues = (
            result["json"].get("issues", []) if isinstance(result["json"], dict) else []
        )
        if not isinstance(issues, list):
            issues = []
        return {
            "section_id": section_id,
            "text": text,
            "issues": issues,
            "backend": "qwen",
            "raw": result["json"],
        }

    async def review_table(
        self,
        table_rows: Sequence[Dict[str, Any]],
        *,
        section_id: Any = None,
        doc_type: str = "学位论文",
        degree_level: str = "学士",
        institution: str = "中国计量大学",
        strictness: int = 3,
    ) -> Dict[str, Any]:
        request = build_table_validation_request(
            table_rows,
            section_id=section_id,
            doc_type=doc_type,
            degree_level=degree_level,
            institution=institution,
            strictness=strictness,
        )
        result = await self.chat(
            messages=request.messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            response_format=request.response_format,
        )
        payload = result["json"] if isinstance(result["json"], dict) else {}
        table_issues = (
            payload.get("table_issues", []) if isinstance(payload, dict) else []
        )
        field_summary = (
            payload.get("field_summary", {}) if isinstance(payload, dict) else {}
        )
        critical_gaps = (
            payload.get("critical_gaps", []) if isinstance(payload, dict) else []
        )
        if not isinstance(table_issues, list):
            table_issues = []
        if not isinstance(field_summary, dict):
            field_summary = {}
        if not isinstance(critical_gaps, list):
            critical_gaps = []
        return {
            "section_id": section_id,
            "table_rows": list(table_rows),
            "table_issues": table_issues,
            "field_summary": field_summary,
            "critical_gaps": critical_gaps,
            "backend": "qwen",
            "raw": result["json"],
        }

    async def verify_reference(
        self,
        reference_text: str,
        retrieved: Sequence[Dict[str, Any]],
        *,
        backend_hint: str = "qwen",
    ) -> Dict[str, Any]:
        request = build_reference_request(reference_text, retrieved)
        result = await self.chat(
            messages=request.messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            response_format=request.response_format,
        )
        verdict = (
            result["json"].get("verdict", "unverified")
            if isinstance(result["json"], dict)
            else "unverified"
        )
        reason = (
            result["json"].get("reason") if isinstance(result["json"], dict) else None
        )
        matched = (
            result["json"].get("matched") if isinstance(result["json"], dict) else None
        )
        return {
            "reference": reference_text,
            "retrieved": list(retrieved),
            "verdict": verdict,
            "reason": reason or result["json"].get("raw", ""),
            "matched": matched,
            "backend": backend_hint,
            "llm_backend": "qwen",
        }


def build_qwen_client() -> QwenClient:
    return QwenClient()
