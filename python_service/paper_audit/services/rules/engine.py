from __future__ import annotations

from .common import DEFAULT_FOCUS_AREAS, extract_text_from_parsed_data
from .consistency import check_consistency_rules
from .document import check_document_rules
from .references import check_reference_content_rules, detect_reference_entries
from .table import check_table_rules
from .text import check_text_rules

__all__ = [
    "DEFAULT_FOCUS_AREAS",
    "check_consistency_rules",
    "check_document_rules",
    "check_reference_content_rules",
    "check_table_rules",
    "check_text_rules",
    "detect_reference_entries",
    "extract_text_from_parsed_data",
]
