"""Concrete evidence binding for source-grounded GOODS fallback (PILOT-001-D04.2).

PILOT-001-D04 made deterministic fallback claims source-bound at corpus level.
A fresh GOODS run exposed the remaining gap: retained requirement rows could name
a human-readable source while trace.evidence_map stayed empty. This compatibility
layer runs after D04 and binds each retained GOODS requirement to a stable
file_id-based evidence reference. When a concrete document cannot be resolved,
the row fails closed instead of remaining a material unsupported assertion.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any, Iterable

from src.modules.tender_operator_agent_demo import upload_service_legacy as _legacy
from src.modules.tender_operator_agent_demo import grounded_fallback_patch as _d04


_INSTALLED = False
_ORIGINAL_OUTPUT_PAYLOADS: Any = None
_BINDING_POLICY = "goods_claim_evidence_binding_v1"
_INSUFFICIENT_TITLE = "INSUFFICIENT_EVIDENCE"

_STOPWORDS = {
    "для",
    "или",
    "как",
    "при",
    "что",
    "это",
    "быть",
    "должен",
    "должна",
    "должны",
    "требуется",
    "требование",
    "товар",
    "товара",
    "товары",
    "поставка",
    "поставки",
    "закупки",
}


@dataclass(frozen=True)
class EvidenceCandidate:
    evidence_id: str
    file_id: str
    source_document: str
    locator: str
    text: str


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize(value: Any) -> str:
    text = _clean(value).lower().replace("ё", "е")
    text = re.sub(r"[^a-zа-я0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(value: Any) -> set[str]:
    return {
        token
        for token in _normalize(value).split()
        if len(token) >= 3 and token not in _STOPWORDS
    }


def _chunk_text(chunk: Any) -> str:
    if not isinstance(chunk, dict):
        return ""
    for key in ("text", "chunk_text", "content"):
        value = _clean(chunk.get(key))
        if value:
            return value
    return ""


def _chunk_locator(chunk: dict[str, Any], *, index: int) -> str:
    locator = chunk.get("locator")
    if isinstance(locator, str) and _clean(locator):
        return _clean(locator)
    if isinstance(locator, dict):
        parts = [f"{key}={_clean(value)}" for key, value in sorted(locator.items()) if _clean(value)]
        if parts:
            return "; ".join(parts)
    for key in ("page", "page_number", "section", "heading", "member", "path"):
        value = _clean(chunk.get(key))
        if value:
            return f"{key}:{value}"
    return f"chunk:{index}"


def _candidate_id(file_id: str, chunk: dict[str, Any] | None, *, index: int | None = None) -> str:
    if chunk:
        for key in ("evidence_id", "chunk_id", "id"):
            value = _clean(chunk.get(key))
            if value:
                return value
    if index is None:
        return f"{file_id}::document"
    return f"{file_id}::chunk:{index}"


def _document_candidates(documents: Iterable[Any]) -> list[EvidenceCandidate]:
    candidates: list[EvidenceCandidate] = []
    for ordinal, document in enumerate(documents, start=1):
        file_id = _clean(getattr(document, "file_id", "")) or f"document-{ordinal}"
        source_document = _clean(getattr(document, "display_name", "")) or file_id
        document_text = _clean(getattr(document, "text", ""))
        chunks = getattr(document, "evidence_chunks", None)
        if isinstance(chunks, list):
            for index, chunk in enumerate(chunks, start=1):
                if not isinstance(chunk, dict):
                    continue
                text = _chunk_text(chunk)
                if not text:
                    continue
                candidates.append(
                    EvidenceCandidate(
                        evidence_id=_candidate_id(file_id, chunk, index=index),
                        file_id=file_id,
                        source_document=source_document,
                        locator=_chunk_locator(chunk, index=index),
                        text=text,
                    )
                )
        if document_text:
            candidates.append(
                EvidenceCandidate(
                    evidence_id=_candidate_id(file_id, None),
                    file_id=file_id,
                    source_document=source_document,
                    locator="document",
                    text=document_text,
                )
            )
    return candidates


def _row_claim(row: dict[str, Any]) -> str:
    parts = [
        _clean(row.get(key))
        for key in ("title", "requirement", "name", "detail", "description", "value")
    ]
    return ". ".join(part for part in parts if part)


def _candidate_score(claim: str, candidate: EvidenceCandidate, *, source_hint: str = "") -> float:
    claim_norm = _normalize(claim)
    evidence_norm = _normalize(candidate.text)
    if not claim_norm or not evidence_norm:
        return 0.0

    score = 0.0
    if claim_norm in evidence_norm:
        score += 5.0

    claim_tokens = _tokens(claim)
    evidence_tokens = _tokens(candidate.text)
    if claim_tokens:
        overlap = len(claim_tokens & evidence_tokens)
        score += overlap / len(claim_tokens) * 4.0
        if overlap >= 2:
            score += 1.0

    themes = _d04._mentioned_themes(claim)
    if themes and all(_d04._evidence_supports(evidence_norm, theme) for theme in themes):
        score += 3.0

    source_hint_norm = _normalize(source_hint)
    if source_hint_norm and source_hint_norm in _normalize(candidate.source_document):
        score += 2.0

    # Prefer a precise chunk over whole-document fallback when both support the claim.
    if candidate.locator != "document":
        score += 0.25
    return score


def _best_candidate(row: dict[str, Any], candidates: list[EvidenceCandidate]) -> EvidenceCandidate | None:
    claim = _row_claim(row)
    if not claim or claim.startswith(_INSUFFICIENT_TITLE):
        return None
    source_hint = _clean(row.get("source") or row.get("source_document"))
    scored = [
        (_candidate_score(claim, candidate, source_hint=source_hint), candidate)
        for candidate in candidates
    ]
    scored = [item for item in scored if item[0] > 0]
    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[1].evidence_id), reverse=True)
    best_score, best = scored[0]

    # D04 already established corpus-level grounding. D04.2 still requires
    # enough claim/document affinity to identify one concrete source safely.
    if best_score < 2.0:
        return None
    return best


def _excerpt(text: str, claim: str, *, limit: int = 320) -> str:
    clean = _clean(text)
    if len(clean) <= limit:
        return clean
    tokens = list(_tokens(claim))
    lowered = clean.lower().replace("ё", "е")
    positions = [lowered.find(token) for token in tokens if lowered.find(token) >= 0]
    start = max(0, min(positions) - 80) if positions else 0
    return clean[start : start + limit].strip()


def _insufficient_row(row: dict[str, Any]) -> dict[str, Any]:
    failed = dict(row)
    failed["title"] = _INSUFFICIENT_TITLE
    failed["detail"] = "Не удалось привязать fallback-требование к конкретному документу закупки."
    failed["evidence_ids"] = []
    failed["evidence_state"] = "insufficient"
    failed.pop("source_document", None)
    return failed


def _bind_requirement_rows(
    rows: Iterable[Any],
    *,
    candidates: list[EvidenceCandidate],
    evidence_map: dict[str, Any],
) -> list[Any]:
    bound_rows: list[Any] = []
    for raw in rows:
        if not isinstance(raw, dict):
            bound_rows.append(raw)
            continue
        row = dict(raw)
        claim = _row_claim(row)
        if not claim or claim.startswith(_INSUFFICIENT_TITLE):
            bound_rows.append(row)
            continue
        candidate = _best_candidate(row, candidates)
        if candidate is None:
            bound_rows.append(_insufficient_row(row))
            continue
        row["evidence_ids"] = [candidate.evidence_id]
        row["source"] = candidate.source_document
        row["source_document"] = candidate.source_document
        row["evidence_state"] = "bound"
        evidence_map[candidate.evidence_id] = {
            "file_id": candidate.file_id,
            "source_document": candidate.source_document,
            "locator": candidate.locator,
            "excerpt": _excerpt(candidate.text, claim),
        }
        bound_rows.append(row)
    return bound_rows


def _bind_fallback_evidence(outputs: dict[str, Any], *, documents: list[Any]) -> dict[str, Any]:
    patched = deepcopy(outputs)
    trace = patched.get("trace")
    if not isinstance(trace, dict):
        return patched
    if trace.get("grounding_policy") != "source_bound_v1":
        return patched
    if str(trace.get("fallback_category") or "").upper() != "GOODS":
        return patched

    candidates = _document_candidates(documents)
    evidence_map = dict(trace.get("evidence_map") or {}) if isinstance(trace.get("evidence_map"), dict) else {}

    requirements = patched.get("requirements")
    if isinstance(requirements, dict) and isinstance(requirements.get("requirements"), list):
        requirements = dict(requirements)
        requirements["requirements"] = _bind_requirement_rows(
            requirements["requirements"],
            candidates=candidates,
            evidence_map=evidence_map,
        )
        patched["requirements"] = requirements

    trace = dict(trace)
    trace["evidence_map"] = evidence_map
    trace["fallback_evidence_binding_policy"] = _BINDING_POLICY
    trace["fallback_evidence_binding_count"] = len(evidence_map)
    trace["fallback_evidence_binding_complete"] = all(
        not isinstance(row, dict)
        or _row_claim(row).startswith(_INSUFFICIENT_TITLE)
        or bool(row.get("evidence_ids"))
        for row in (
            patched.get("requirements", {}).get("requirements", [])
            if isinstance(patched.get("requirements"), dict)
            else []
        )
    )
    patched["trace"] = trace
    return patched


def _build_output_payloads(*args: Any, **kwargs: Any) -> dict[str, Any]:
    outputs = _ORIGINAL_OUTPUT_PAYLOADS(*args, **kwargs)
    documents = kwargs.get("documents")
    if documents is None and len(args) >= 2:
        documents = args[1]
    return _bind_fallback_evidence(outputs, documents=list(documents or []))


def install() -> None:
    """Install D04.2 after D04/D04.1 wrappers exactly once."""
    global _INSTALLED
    global _ORIGINAL_OUTPUT_PAYLOADS
    if _INSTALLED:
        return
    _ORIGINAL_OUTPUT_PAYLOADS = _legacy._build_output_payloads
    _legacy._build_output_payloads = _build_output_payloads
    _INSTALLED = True
