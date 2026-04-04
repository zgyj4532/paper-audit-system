from __future__ import annotations

import ctypes
import hashlib
import math
import os
import re
import sys
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any, Dict, List

import chromadb

from ...config import settings

_EMBEDDING_DIMENSION = 64


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[\w\u4e00-\u9fff]+", text.lower())


def embed_text(text: str, dimension: int = _EMBEDDING_DIMENSION) -> List[float]:
    vector = [0.0] * dimension
    for token in _tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        vector[index] += 1.0

    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [value / norm for value in vector]
    return vector


def get_system_memory_mb() -> int | None:
    if sys.platform.startswith("linux") or sys.platform.startswith("darwin"):
        try:
            if hasattr(os, "sysconf"):
                pages = os.sysconf("SC_PHYS_PAGES")
                page_size = os.sysconf("SC_PAGE_SIZE")
                return int((pages * page_size) / (1024 * 1024))
        except Exception:
            return None
        return None

    if sys.platform.startswith("win"):
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            state = MEMORYSTATUSEX()
            state.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
                return int(state.ullTotalPhys / (1024 * 1024))
        except Exception:
            return None
    return None


def estimated_bge_small_zh_runtime_ram_mb() -> int:
    return int(settings.LOCAL_REFERENCE_VERIFIER_ESTIMATED_RAM_MB)


def can_use_local_reference_verifier() -> bool:
    total_mb = get_system_memory_mb()
    if total_mb is None:
        return False
    return total_mb >= int(settings.LOCAL_REFERENCE_VERIFIER_MIN_RAM_MB)


def resolve_reference_verifier_backend() -> str:
    backend = str(getattr(settings, "REFERENCE_VERIFIER_BACKEND", "auto")).strip().lower()
    if backend in {"local", "qwen"}:
        return backend
    if backend == "auto":
        return "local" if can_use_local_reference_verifier() else "qwen"
    return "qwen"


def _join_authors(authors: Any) -> str:
    if isinstance(authors, (list, tuple)):
        return ", ".join(str(author) for author in authors if author)
    if authors:
        return str(authors)
    return ""


def paper_text_from_payload(payload: Dict[str, Any]) -> str:
    parts = [
        str(payload.get("title", "")),
        _join_authors(payload.get("authors")),
        str(payload.get("journal", "")),
        str(payload.get("year", "")),
        str(payload.get("doi", "")),
        str(payload.get("text", "")),
        str(payload.get("abstract", "")),
    ]
    return "\n".join(part for part in parts if part)


def _normalize_for_similarity(text: str) -> set[str]:
    return set(_tokenize(text))


def _compact_text(text: str) -> str:
    return "".join(_tokenize(text))


def _similarity_score(left: str, right: str) -> float:
    left_tokens = _normalize_for_similarity(left)
    right_tokens = _normalize_for_similarity(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _prefix_similarity(left: str, right: str) -> float:
    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0

    matched = 0
    for left_token, right_token in zip(left_tokens, right_tokens):
        if left_token != right_token:
            break
        matched += 1

    if matched == 0:
        return 0.0
    return matched / min(len(left_tokens), len(right_tokens))


def _extract_years(text: str) -> List[str]:
    return re.findall(r"(?:19|20)\d{2}", text)


def _extract_reference_fragments(text: str) -> List[str]:
    fragments: List[str] = []
    for fragment in re.split(r"[，,。.;；\n]+", text):
        cleaned = fragment.strip()
        if len(_tokenize(cleaned)) < 3:
            continue
        if _extract_years(cleaned):
            continue
        fragments.append(cleaned)
    return fragments


def _candidate_text(candidate: Dict[str, Any]) -> str:
    metadata = candidate.get("metadata", {}) if isinstance(candidate, dict) else {}
    document = candidate.get("document", "") if isinstance(candidate, dict) else ""
    parts = [
        str(metadata.get("title", "")),
        str(metadata.get("authors", "")),
        str(metadata.get("journal", "")),
        str(metadata.get("year", "")),
        str(metadata.get("doi", "")),
        str(document or ""),
    ]
    return "\n".join(part for part in parts if part)


def verify_reference_locally(reference_text: str, retrieved: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    text = str(reference_text or "").strip()
    if not text:
        return {
            "reference": {"text": text},
            "retrieved": retrieved or [],
            "verdict": "unverified",
            "confidence": "low",
            "reason": "empty_reference",
            "risk_flags": ["empty_reference"],
            "llm_backend": "local",
        }

    candidates = list(retrieved) if retrieved is not None else query_papers(text, n_results=3)
    if not candidates:
        return {
            "reference": {"text": text},
            "retrieved": [],
            "verdict": "unverified",
            "confidence": "low",
            "reason": "no_local_match",
            "risk_flags": ["no_local_match"],
            "llm_backend": "local",
        }

    best_candidate = None
    best_score = -1.0
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        score = _similarity_score(text, _candidate_text(candidate))
        if score > best_score:
            best_score = score
            best_candidate = candidate

    metadata = best_candidate.get("metadata", {}) if isinstance(best_candidate, dict) else {}
    candidate_document = best_candidate.get("document", "") if isinstance(best_candidate, dict) else ""
    candidate_text = _candidate_text(best_candidate or {})
    reference_years = _extract_years(text)
    candidate_year = str(metadata.get("year", "")).strip()
    year_mismatch = bool(reference_years and candidate_year and candidate_year not in reference_years)

    title_text = str(metadata.get("title", "")).strip()
    title_score = _similarity_score(text, title_text) if title_text else 0.0
    if title_text and _compact_text(title_text) in _compact_text(text):
        title_score = max(title_score, 1.0)
    if title_text:
        title_score = max(title_score, _prefix_similarity(text, title_text), _prefix_similarity(title_text, text))
        for fragment in _extract_reference_fragments(text):
            title_score = max(
                title_score,
                _similarity_score(fragment, title_text),
                _prefix_similarity(fragment, title_text),
                _prefix_similarity(title_text, fragment),
            )

    author_score = _similarity_score(text, str(metadata.get("authors", ""))) if metadata.get("authors") else 0.0
    document_score = _similarity_score(text, candidate_text)
    best_score = max(best_score, title_score, author_score, document_score)

    if best_score >= 0.85 and not year_mismatch:
        verdict = "verified"
        confidence = "high"
        reason = "local_match_strong"
        risk_flags: List[str] = []
    elif best_score >= 0.65 and not year_mismatch:
        verdict = "needs_review"
        confidence = "medium"
        reason = "local_match_partial"
        risk_flags = ["partial_match"]
    else:
        verdict = "unverified"
        confidence = "low" if best_score < 0.45 else "medium"
        reason = "local_match_weak"
        risk_flags = ["weak_match"]

    discrepancies = []
    if year_mismatch:
        discrepancies.append(
            {
                "field": "year",
                "cited": ",".join(reference_years),
                "actual": candidate_year,
            }
        )
        risk_flags.append("year_mismatch")

    matched_title = metadata.get("title")
    if not matched_title and candidate_document:
        matched_title = candidate_document.splitlines()[0]

    matched_record = {
        "title": matched_title,
        "authors": [author.strip() for author in str(metadata.get("authors", "")).split(",") if author.strip()],
        "year": metadata.get("year"),
        "similarity_score": round(best_score, 4),
    }

    return {
        "reference": {"text": text},
        "retrieved": candidates,
        "verdict": verdict,
        "confidence": confidence,
        "matched_record": matched_record,
        "discrepancies": discrepancies,
        "reason": reason,
        "risk_flags": risk_flags,
        "llm_backend": "local",
        "backend": "local",
        "similarity_score": round(best_score, 4),
        "candidate_text": candidate_text,
    }


@dataclass(slots=True)
class VectorStore:
    persist_dir: str | None = None
    collection_name: str | None = None
    _client: Any = field(init=False, repr=False)
    _collection: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.persist_dir = self.persist_dir or str(settings.CHROMA_PERSIST_DIR)
        self.collection_name = self.collection_name or settings.CHROMA_COLLECTION_NAME
        Path(self.persist_dir).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=self.persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def collection(self):
        return self._collection

    def index_paper(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        text = paper_text_from_payload(payload)
        if not text.strip():
            raise ValueError("paper payload must include at least one text field")

        paper_id = str(
            payload.get("id")
            or payload.get("paper_id")
            or hashlib.sha1(text.encode("utf-8")).hexdigest()
        )
        metadata = {
            "title": payload.get("title", ""),
            "authors": _join_authors(payload.get("authors")),
            "year": int(payload.get("year")) if payload.get("year") is not None else None,
            "journal": payload.get("journal", ""),
            "doi": payload.get("doi", ""),
            "source": payload.get("source", "user_upload"),
            "embedding_model": payload.get("embedding_model", "simple-hash-embedding-v1"),
        }
        metadata = {key: value for key, value in metadata.items() if value not in (None, "")}

        self._collection.upsert(
            ids=[paper_id],
            documents=[text],
            embeddings=[embed_text(text)],
            metadatas=[metadata],
        )

        return {
            "paper_id": paper_id,
            "collection_name": self.collection_name,
            "embedding_model": metadata.get("embedding_model"),
            "metadata": metadata,
        }

    def query(self, text: str, n_results: int = 3) -> List[Dict[str, Any]]:
        if not text.strip():
            return []

        results = self._collection.query(
            query_embeddings=[embed_text(text)],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        ids = results.get("ids", [[]])[0] if isinstance(results, dict) else []
        documents = results.get("documents", [[]])[0] if isinstance(results, dict) else []
        metadatas = results.get("metadatas", [[]])[0] if isinstance(results, dict) else []
        distances = results.get("distances", [[]])[0] if isinstance(results, dict) else []

        rows: List[Dict[str, Any]] = []
        for index, paper_id in enumerate(ids):
            rows.append(
                {
                    "id": paper_id,
                    "document": documents[index] if index < len(documents) else None,
                    "metadata": metadatas[index] if index < len(metadatas) else {},
                    "distance": distances[index] if index < len(distances) else None,
                }
            )
        return rows


def get_collection():
    return VectorStore().collection


def index_paper(payload: Dict[str, Any]) -> Dict[str, Any]:
    return VectorStore().index_paper(payload)


def query_papers(text: str, n_results: int = 3) -> List[Dict[str, Any]]:
    return VectorStore().query(text, n_results=n_results)
