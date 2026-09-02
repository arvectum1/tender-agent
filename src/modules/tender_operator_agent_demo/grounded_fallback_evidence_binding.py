"""Concrete evidence binding for source-grounded GOODS fallback (PILOT-001-D04.2).

PILOT-001-D04 removed unsupported fallback templates at corpus/theme level. A
fresh GOODS run exposed the remaining provenance gap: retained requirements could
still have only a human-readable source label and an empty evidence map. This
post-D04 compatibility layer binds every retained GOODS requirement to one
stable file/chunk evidence reference, and fails closed when the concrete claim
cannot be matched to a source document.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from src.modules.tender_operator_agent_demo import grounded_fallback_patch as _d04
from src.modules.tender_operator_agent_demo import upload_service_legacy as _legacy

_INSTALLED = False
_ORIGINAL_OUTPUT_PAYLOADS: Any = None
_BINDING_POLICY = "goods_claim_evidence_binding_v1"
_MATCHING_POLICY = "semantic_concrete_v1"
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


def _numbers(value: Any) -> set[str]:
    normalized = _clean(value).replace(" ", "").replace(",", ".")
    return set(re.findall(r"(?<![A-Za-zА-Яа-яЁё])\d+(?:\.\d+)?", normalized))


_GENERIC_TOKENS = {
    "соответствие",
    "соответствовать",
    "требование",
    "требования",
    "качество",
    "продукция",
    "изделие",
    "оборудование",
    "документация",
    "заказчик",
}
_STANDARD_PATTERN = re.compile(
    r"\b(?:ГОСТ(?:\s*Р)?|ТУ|ТР\s*ТС|ЕАЭС|СП|СНиП|ISO|IEC|DIN)\b(?:\s*[№N]?\s*[A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9./-]*)*",
    re.IGNORECASE,
)
_STANDARD_ID_PATTERN = re.compile(
    r"\b(?:ГОСТ(?:\s*Р)?|ТУ|ТР\s*ТС|ЕАЭС|СП|СНиП|ISO|IEC|DIN)\s*[№N]?\s*[A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9./-]*",
    re.IGNORECASE,
)
_NUMBER_UNIT_PATTERN = re.compile(
    r"(?<!\w)(\d+(?:[.,]\d+)?)\s*(%|кв\.\s*м|м²|м2|мм|см|м|квт|кВт|в|а|шт\.?|ед\.?|дн(?:я|ей)?|рабочих?\s+дн(?:я|ей)?|календарных?\s+дн(?:я|ей)?|месяц(?:ев|а)?|лет|года?|руб(?:лей)?|₽)?",
    re.IGNORECASE,
)
_CONCEPT_GROUPS = (
    ("safety", ("безопасност", "пожарн", "электробезопасност", "сертификат", "декларац", "испытан", "класс защиты", "степен[ьи] защиты")),
    ("delivery", ("срок поставки", "место поставки", "доставк", "партия", "график поставки", "приемк", "приёмк", "разгруз")),
)


def _normalized_standard_ids(value: Any) -> set[str]:
    return {
        re.sub(r"[\s.,;:]+", "", item.upper().replace("Ё", "Е"))
        for item in _STANDARD_ID_PATTERN.findall(_clean(value))
    }


def _number_units(value: Any) -> list[tuple[str, str, int]]:
    text = _STANDARD_ID_PATTERN.sub(" ", _clean(value))
    text = re.sub(r"\bip\s*\d{2}\b", " ", text, flags=re.IGNORECASE)
    text = text.replace(",", ".")
    return [(number, re.sub(r"\s+", " ", unit.lower()).strip(" ."), match.start()) for match in _NUMBER_UNIT_PATTERN.finditer(text) for number, unit in [(match.group(1), match.group(2) or "")]]


def _numeric_anchors_supported(claim: str, evidence: str) -> bool:
    claim_numbers = _number_units(claim)
    if not claim_numbers:
        return True
    evidence_numbers = _number_units(evidence)
    evidence_text = _normalize(evidence)
    for number, unit, position in claim_numbers:
        matching = [(epos, eunit) for enumber, eunit, epos in evidence_numbers if enumber == number and (not unit or eunit == unit)]
        if not matching:
            return False
        claim_context = _tokens(claim[max(0, position - 45) : position + 45]) - _GENERIC_TOKENS
        if claim_context and not any(
            claim_context & (_tokens(evidence[max(0, epos - 60) : epos + 60]) - _GENERIC_TOKENS)
            for epos, _ in matching
        ):
            return False
    return bool(evidence_text)


def _concept_anchors(value: Any) -> set[str]:
    normalized = _normalize(value)
    anchors: set[str] = set()
    for name, patterns in _CONCEPT_GROUPS:
        if any(pattern in normalized for pattern in patterns):
            anchors.add(name)
    if re.search(r"\bip\s*\d{2}\b", normalized):
        anchors.add("ip_rating")
    return anchors


def _semantic_anchors_supported(claim: str, evidence: str) -> bool:
    claim_normalized = _normalize(claim)
    evidence_normalized = _normalize(evidence)
    if not claim_normalized or not evidence_normalized:
        return False

    standard_ids = _normalized_standard_ids(claim)
    if standard_ids and not standard_ids.issubset(_normalized_standard_ids(evidence)):
        return False
    if not _numeric_anchors_supported(claim, evidence):
        return False

    claim_concepts = _concept_anchors(claim)
    evidence_concepts = _concept_anchors(evidence)
    if not claim_concepts.issubset(evidence_concepts):
        return False
    claim_ip = re.findall(r"\bip\s*\d{2}\b", claim_normalized)
    if claim_ip and not set(claim_ip).issubset(set(re.findall(r"\bip\s*\d{2}\b", evidence_normalized))):
        return False

    # Concrete standards, numbers, safety/delivery concepts, and model-like
    # tokens must be present in the evidence itself. Generic vocabulary never
    # upgrades a candidate to a factual binding.
    concrete_tokens = _tokens(claim) - _GENERIC_TOKENS
    evidence_tokens = _tokens(evidence)
    if standard_ids or claim_concepts or _number_units(claim):
        if concrete_tokens <= evidence_tokens:
            return True
        return bool(evidence_tokens & concrete_tokens) and (
            bool(standard_ids or _number_units(claim))
            or len(evidence_tokens & concrete_tokens) / len(concrete_tokens) >= 0.60
        )
    if len(concrete_tokens) < 2:
        return False
    return len(concrete_tokens & evidence_tokens) / len(concrete_tokens) >= 0.60


def _chunk_text(chunk: Any) -> str:
    if not isinstance(chunk, dict):
        return ""
    for key in ("text", "chunk_text", "content"):
        text = _clean(chunk.get(key))
        if text:
            return text
    return ""


def _chunk_locator(chunk: dict[str, Any], index: int) -> str:
    locator = chunk.get("locator")
    if isinstance(locator, str) and _clean(locator):
        return _clean(locator)
    if isinstance(locator, dict):
        parts = [
            f"{key}={_clean(value)}"
            for key, value in sorted(locator.items())
            if _clean(value)
        ]
        if parts:
            return "; ".join(parts)
    for key in ("page", "page_number", "section", "heading", "member", "path"):
        value = _clean(chunk.get(key))
        if value:
            return f"{key}:{value}"
    return f"chunk:{index}"


def _evidence_id(file_id: str, chunk: dict[str, Any] | None, index: int | None) -> str:
    if chunk:
        for key in ("evidence_id", "chunk_id", "id"):
            value = _clean(chunk.get(key))
            if value:
                return value
    return f"{file_id}::document" if index is None else f"{file_id}::chunk:{index}"


def _document_candidates(documents: Iterable[Any]) -> list[EvidenceCandidate]:
    candidates: list[EvidenceCandidate] = []
    for ordinal, document in enumerate(documents, start=1):
        file_id = _clean(getattr(document, "file_id", "")) or f"document-{ordinal}"
        source_document = _clean(getattr(document, "display_name", "")) or file_id
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
                        evidence_id=_evidence_id(file_id, chunk, index),
                        file_id=file_id,
                        source_document=source_document,
                        locator=_chunk_locator(chunk, index),
                        text=text,
                    )
                )
        document_text = _clean(getattr(document, "text", ""))
        if document_text:
            candidates.append(
                EvidenceCandidate(
                    evidence_id=_evidence_id(file_id, None, None),
                    file_id=file_id,
                    source_document=source_document,
                    locator="document",
                    text=document_text,
                )
            )
    return candidates


def _row_claim(row: dict[str, Any]) -> str:
    return ". ".join(
        value
        for value in (
            _clean(row.get(key))
            for key in ("title", "requirement", "name", "detail", "description", "value")
        )
        if value
    )


def _claim_matches_candidate(claim: str, candidate: EvidenceCandidate) -> bool:
    claim_norm = _normalize(claim)
    evidence_norm = _normalize(candidate.text)
    if not claim_norm or not evidence_norm:
        return False

    if not _semantic_anchors_supported(claim, candidate.text):
        return False

    if claim_norm in evidence_norm:
        return True

    claim_tokens = _tokens(claim)
    evidence_tokens = _tokens(candidate.text)
    overlap = claim_tokens & evidence_tokens
    if not claim_tokens:
        return False

    # Theme/source labels alone must never bind a material claim.
    minimum_overlap = 1 if len(claim_tokens) == 1 else 2
    if len(overlap) < minimum_overlap:
        return False

    # For longer claims, require enough of the actual assertion to be present.
    return not (len(claim_tokens) >= 4 and len(overlap) / len(claim_tokens) < 0.40)


def _candidate_score(claim: str, candidate: EvidenceCandidate, source_hint: str) -> float:
    if not _claim_matches_candidate(claim, candidate):
        return 0.0
    claim_norm = _normalize(claim)
    evidence_norm = _normalize(candidate.text)
    claim_tokens = _tokens(claim)
    evidence_tokens = _tokens(candidate.text)
    score = 5.0 if claim_norm in evidence_norm else 0.0
    if claim_tokens:
        overlap = len(claim_tokens & evidence_tokens)
        score += overlap / len(claim_tokens) * 4.0
    themes = _d04._mentioned_themes(claim)
    if themes and all(_d04._evidence_supports(evidence_norm, theme) for theme in themes):
        score += 1.0
    if source_hint and _normalize(source_hint) in _normalize(candidate.source_document):
        score += 1.0
    if candidate.locator != "document":
        score += 0.25
    return score


def _best_candidate(row: dict[str, Any], candidates: list[EvidenceCandidate]) -> EvidenceCandidate | None:
    claim = _row_claim(row)
    if not claim or claim.startswith(_INSUFFICIENT_TITLE):
        return None
    source_hint = _clean(row.get("source") or row.get("source_document"))
    scored = []
    for candidate in candidates:
        excerpt = _excerpt(candidate.text, claim)
        if not _semantic_anchors_supported(claim, excerpt):
            continue
        score = _candidate_score(claim, candidate, source_hint)
        if score:
            scored.append((score, candidate))
    scored = [item for item in scored if item[0] > 0]
    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[1].evidence_id), reverse=True)
    return scored[0][1]


def _excerpt(text: str, claim: str, limit: int = 320) -> str:
    clean = _clean(text)
    if len(clean) <= limit:
        return clean
    lowered = clean.lower().replace("ё", "е")
    positions = [lowered.find(token) for token in _tokens(claim) if lowered.find(token) >= 0]
    start = max(0, min(positions) - 80) if positions else 0
    return clean[start : start + limit].strip()


def _insufficient_row(row: dict[str, Any]) -> dict[str, Any]:
    failed = dict(row)
    for key in ("requirement", "name", "description", "value", "source_document"):
        failed.pop(key, None)
    failed["title"] = _INSUFFICIENT_TITLE
    failed["detail"] = "Не удалось привязать fallback-требование к конкретному документу закупки."
    failed["source"] = "Документы закупки"
    failed["evidence_ids"] = []
    failed["evidence_state"] = "insufficient"
    return failed


def _bind_requirement_rows(
    rows: Iterable[Any],
    *,
    candidates: list[EvidenceCandidate],
    evidence_map: dict[str, Any],
) -> list[Any]:
    result: list[Any] = []
    for raw in rows:
        if not isinstance(raw, dict):
            result.append(raw)
            continue
        row = dict(raw)
        claim = _row_claim(row)
        if not claim or claim.startswith(_INSUFFICIENT_TITLE):
            result.append(row)
            continue
        candidate = _best_candidate(row, candidates)
        if candidate is None:
            result.append(_insufficient_row(row))
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
        result.append(row)
    return result


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
    evidence_map = (
        dict(trace.get("evidence_map") or {})
        if isinstance(trace.get("evidence_map"), dict)
        else {}
    )
    requirements = patched.get("requirements")
    if isinstance(requirements, dict) and isinstance(requirements.get("requirements"), list):
        requirements = dict(requirements)
        requirements["requirements"] = _bind_requirement_rows(
            requirements["requirements"],
            candidates=candidates,
            evidence_map=evidence_map,
        )
        patched["requirements"] = requirements

    rows = (
        patched.get("requirements", {}).get("requirements", [])
        if isinstance(patched.get("requirements"), dict)
        else []
    )
    trace = dict(trace)
    trace["evidence_map"] = evidence_map
    trace["fallback_evidence_binding_policy"] = _BINDING_POLICY
    trace["fallback_evidence_matching_policy"] = _MATCHING_POLICY
    trace["fallback_evidence_binding_count"] = len(evidence_map)
    trace["fallback_evidence_binding_complete"] = all(
        not isinstance(row, dict)
        or _row_claim(row).startswith(_INSUFFICIENT_TITLE)
        or bool(row.get("evidence_ids"))
        for row in rows
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
    """Install D04.2 after the D04/D04.1 wrappers exactly once."""
    global _INSTALLED
    global _ORIGINAL_OUTPUT_PAYLOADS
    if _INSTALLED:
        return
    _ORIGINAL_OUTPUT_PAYLOADS = _legacy._build_output_payloads
    _legacy._build_output_payloads = _build_output_payloads
    _INSTALLED = True
