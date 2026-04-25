from __future__ import annotations

import logging
from typing import Any, Dict, List, TypedDict

from ... import config as _config
from ..llm import build_qwen_client, normalize_focus_areas
from ..rules import (
    audit_document_via_java_http,
    check_consistency_rules,
    check_table_rules,
    check_text_rules,
    detect_reference_entries,
    normalize_java_audit_response,
    review_document as review_document_via_rules,
)
from ..vector import (
    can_use_local_reference_verifier,
    query_papers,
    resolve_reference_verifier_backend,
    verify_reference_locally,
)
from .java import review_document_java_http as _review_document_java_http_impl
from .local import review_document_local as _review_document_local_impl
from .local import verify_references as _verify_references_impl
from .shared import (
    collect_java_blacklisted_section_ids,
    filter_parsed_sections,
    merge_hybrid_reviews,
    rules_backend,
    split_into_chunks,
)

logger = logging.getLogger(__name__)
settings = _config.settings


class AuditState(TypedDict, total=False):
    parsed_data: Dict[str, Any]
    source_file: str
    chunks: List[Dict[str, Any]]
    chunk_reviews: List[Dict[str, Any]]
    reference_verification: List[Dict[str, Any]]
    consistency_issues: List[Dict[str, Any]]
    summary: Dict[str, Any]
    backend: str


async def _review_document_java_http(
    parsed_data: Dict[str, Any], source_file: str | None = None
) -> Dict[str, Any]:
    return await _review_document_java_http_impl(
        parsed_data,
        source_file=source_file,
        audit_java=audit_document_via_java_http,
        normalize_java_response=normalize_java_audit_response,
        split_chunks=split_into_chunks,
        detect_refs=detect_reference_entries,
    )


async def _review_document_local(
    parsed_data: Dict[str, Any], source_file: str | None = None
) -> Dict[str, Any]:
    return await _review_document_local_impl(
        parsed_data,
        source_file=source_file,
        build_client=build_qwen_client,
        normalize_areas=normalize_focus_areas,
        split_chunks=split_into_chunks,
        check_text=check_text_rules,
        check_table=check_table_rules,
        check_consistency=check_consistency_rules,
        detect_refs=detect_reference_entries,
        query_papers_fn=query_papers,
        resolve_backend=resolve_reference_verifier_backend,
        verify_local=verify_reference_locally,
        can_use_local=can_use_local_reference_verifier,
    )


async def verify_references(references: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return await _verify_references_impl(
        references,
        build_client=build_qwen_client,
        resolve_backend=resolve_reference_verifier_backend,
        can_use_local=can_use_local_reference_verifier,
        query_papers_fn=query_papers,
        verify_local=verify_reference_locally,
    )


async def review_document(
    parsed_data: Dict[str, Any], source_file: str | None = None
) -> Dict[str, Any]:
    backend = rules_backend()

    if backend == "local":
        return await _review_document_local(parsed_data, source_file=source_file)

    if backend == "hybrid":
        java_review = await _review_document_java_http(
            parsed_data, source_file=source_file
        )
        blacklisted_section_ids = collect_java_blacklisted_section_ids(java_review)
        filtered_parsed_data = filter_parsed_sections(
            parsed_data, blacklisted_section_ids
        )
        ai_review = await _review_document_local(
            filtered_parsed_data, source_file=source_file
        )

        if not blacklisted_section_ids:
            logger.info("Hybrid backend found no Java blacklisted sections")
        else:
            logger.info(
                "Hybrid backend filtered %s Java-reviewed sections for AI review",
                len(blacklisted_section_ids),
            )

        return merge_hybrid_reviews(
            java_review,
            ai_review,
            parsed_data,
            blacklisted_section_ids,
            source_file=source_file,
        )

    if backend != "java_http":
        logger.warning(
            "Unknown RULE_AUDIT_BACKEND=%s, falling back to java_http", backend
        )

    return await review_document_via_rules(parsed_data, source_file=source_file)


def build_workflow():
    try:
        from langgraph.graph import END, StateGraph
    except Exception:
        return None

    graph = StateGraph(AuditState)

    async def splitter_node(state: AuditState) -> Dict[str, Any]:
        parsed_data = state.get("parsed_data", {})
        return {"chunks": split_into_chunks(parsed_data)}

    async def review_node(state: AuditState) -> Dict[str, Any]:
        parsed_data = state.get("parsed_data", {})
        return await review_document(parsed_data, state.get("source_file"))

    graph.add_node("splitter", splitter_node)
    graph.add_node("review", review_node)
    graph.set_entry_point("splitter")
    graph.add_edge("splitter", "review")
    graph.add_edge("review", END)

    return graph.compile()
