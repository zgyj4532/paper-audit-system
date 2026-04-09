from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


def normalize_focus_areas(focus_areas: Iterable[str] | None) -> List[str]:
    areas = [
        str(area).strip()
        for area in (focus_areas or ("typo", "format", "logic", "reference"))
    ]
    return [area for area in areas if area]


def calculate_temperature(task_type: str, strictness: int) -> float:
    base_map = {
        "review_chunk": 0.3,
        "review_table": 0.15,
        "table_validation": 0.15,
        "verify_reference": 0.0,
        "consistency_check": 0.1,
    }
    base = base_map.get(task_type, 0.1)
    adjustment = (3 - strictness) * 0.05
    return max(0.0, min(base + adjustment, 1.0))


def json_pretty(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


@dataclass(slots=True)
class LLMRequest:
    messages: List[Dict[str, str]]
    temperature: float
    max_tokens: int
    response_format: Dict[str, Any] | None = None
