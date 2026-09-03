"""Source-first recall of material commercial terms for PILOT-001-D08.

This layer is deliberately deterministic. It only republishes bounded excerpts
that are present in the registered procurement document text and keeps a
machine-inspectable evidence reference beside every recovered fact. It never
invents supplier-side conditions, risk classifications, or missing dates.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from src.modules.tender_operator_agent_demo import upload_service_legacy as _legacy

_INSTALLED = False
_ORIGINAL_PRELIMINARY: Any | None = None
_MAX_EXCERPT_CHARS = 720
_MAX_FACTS_PER_KIND = 3

_KIND_LABELS = {
    "delivery_period": "Срок поставки",
    "payment_terms": "Условия оплаты",
    "acceptance_signing_deadline": "Срок приёмки / подписания",
}

_DELIVERY_TOPIC = re.compile(
    r"\b(?:срок\w*\s+(?:постав|достав)\w*|(?:постав|достав)\w*\s+(?:товар\w*|продукц\w*)?)\b",
    re.IGNORECASE,
)
_DELIVERY_TIMING = re.compile(
    r"(?:\bв\s+течение\s+\d+|\bне\s+позднее\b|\bне\s+ранее\b|"
    r"\bдо\s+\d{1,2}[.\-/]|\b\d+\s+(?:рабоч\w*|календарн\w*)\s+дн\w*|"
    r"\bс\s+(?:даты|момента)\b|\bпо\s+заявк\w*\b)",
    re.IGNORECASE,
)
_PAYMENT_TOPIC = re.compile(
    r"\b(?:оплат\w*|аванс\w*|предоплат\w*|постоплат\w*|"
    r"перечислени\w*\s+денежн\w*\s+средств\w*|"
    r"расч[её]т\w*\s+(?:с\s+(?:поставщик\w*|подрядчик\w*|исполнитель\w*)|"
    r"между\s+заказчик\w*\s+и\s+(?:поставщик\w*|подрядчик\w*|исполнитель\w*)|"
    r"за\s+(?:поставленн\w*\s+товар\w*|выполненн\w*\s+работ\w*|оказанн\w*\s+услуг\w*)))\b",
    re.IGNORECASE,
)
_PAYMENT_DETAIL = re.compile(
    r"(?:\bв\s+течение\s+\d+|\bне\s+позднее\b|\bпосле\s+(?:при[её]мк\w*|подписан\w*|поставк\w*)|"
    r"\b\d+\s+(?:рабоч\w*|календарн\w*|банковск\w*)\s+дн\w*|"
    r"\b\d+(?:[.,]\d+)?\s*%|\bпоэтап\w*|\без\s+аванс\w*|\bбез\s+предоплат\w*)",
    re.IGNORECASE,
)
_ACCEPTANCE_TOPIC = re.compile(
    r"\b(?:при[её]мк\w*|документ\w*\s+о\s+при[её]мк\w*|"
    r"акт\w*\s+при[её]мк\w*|подпис\w*\s+(?:документ\w*|акт\w*)|"
    r"мотивированн\w*\s+отказ\w*)\b",
    re.IGNORECASE,
)
_ACCEPTANCE_TIMING = re.compile(
    r"(?:\bв\s+течение\s+\d+|\bне\s+позднее\b|"
    r"\b\d+\s+(?:рабоч\w*|календарн\w*)\s+дн\w*|"
    r"\bсрок\w*\s+(?:при[её]мк\w*|подписан\w*)|"
    r"\bподпис\w*\s+(?:в\s+течение|не\s+позднее))",
    re.IGNORECASE,
)


def _normalize(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split()).strip()


def _safe_document_name(document: Any) -> str:
    value = Path(str(getattr(document, "display_name", "") or "")).name.strip()
    if not value or re.fullmatch(r"[0-9a-f]{64}(?:\.[a-z0-9]+)?", value, re.I):
        return "Документ закупки"
    return value


def _eligible_document(document: Any) -> bool:
    role = str(getattr(document, "role", "") or "").casefold()
    name = str(getattr(document, "display_name", "") or "").casefold()
    haystack = f"{role} {name}"
    if any(token in haystack for token in ("price_justification", "обоснование нмцк", "расчет нмцк", "расчёт нмцк")):
        return False
    return any(
        token in haystack
        for token in (
            "contract_draft",
            "draft_contract",
            "контракт",
            "договор",
            "technical_spec",
            "техническ",
            "описание объекта",
            "notice",
            "notification",
            "извещ",
            "supporting",
        )
    )


def _boundary_before(text: str, start: int, radius: int = 320) -> int:
    floor = max(0, start - radius)
    candidates = [text.rfind("\n", floor, start), text.rfind(". ", floor, start), text.rfind("; ", floor, start)]
    boundary = max(candidates)
    if boundary < 0:
        return floor
    return boundary + (2 if text[boundary : boundary + 2] in {". ", "; "} else 1)


def _boundary_after(text: str, end: int, radius: int = 620) -> int:
    ceiling = min(len(text), end + radius)
    candidates = [
        value
        for value in (
            text.find("\n", end, ceiling),
            text.find(". ", end, ceiling),
            text.find("; ", end, ceiling),
        )
        if value >= 0
    ]
    return (min(candidates) + 1) if candidates else ceiling


def _safe_locator(locator: Any) -> dict[str, Any]:
    if not isinstance(locator, dict):
        return {}
    allowed = ("page", "paragraph", "line", "row", "section", "path", "chunk_index", "char_start", "char_end")
    clean: dict[str, Any] = {}
    for key in allowed:
        value = locator.get(key)
        if isinstance(value, (int, str)) and str(value).strip():
            text = str(value).strip()
            if not text.startswith(("/", "file:")) and "/Users/" not in text and "/Volumes/" not in text:
                clean[key] = value
    return clean


def _chunk_reference(document: Any, excerpt: str, start: int, end: int) -> dict[str, Any]:
    document_name = _safe_document_name(document)
    chunks = list(getattr(document, "evidence_chunks", None) or [])
    normalized_excerpt = _normalize(excerpt).casefold()
    anchors = [normalized_excerpt[:120], normalized_excerpt[:80], normalized_excerpt[:48]]
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            continue
        chunk_text = _normalize(str(chunk.get("text") or "")).casefold()
        locator = _safe_locator(chunk.get("locator"))
        loc_start = locator.get("char_start")
        loc_end = locator.get("char_end")
        overlaps = isinstance(loc_start, int) and isinstance(loc_end, int) and loc_start < end and loc_end > start
        contains = any(anchor and anchor in chunk_text for anchor in anchors)
        if not (overlaps or contains):
            continue
        locator.setdefault("chunk_index", index)
        reference = {"document_name": document_name, "locator": locator}
        chunk_id = str(chunk.get("chunk_id") or "").strip()
        if chunk_id:
            reference["chunk_id"] = chunk_id
        return reference
    return {
        "document_name": document_name,
        "locator": {"char_start": start, "char_end": end},
    }


def _source_display(reference: dict[str, Any]) -> str:
    document = str(reference.get("document_name") or "Документ закупки")
    locator = reference.get("locator") if isinstance(reference.get("locator"), dict) else {}
    labels = {
        "page": "страница",
        "paragraph": "абзац",
        "line": "строка",
        "row": "строка таблицы",
        "section": "раздел",
        "path": "раздел",
        "chunk_index": "фрагмент",
    }
    details: list[str] = []
    for key, label in labels.items():
        if key in locator:
            details.append(f"{label}: {locator[key]}")
    if not details and isinstance(locator.get("char_start"), int) and isinstance(locator.get("char_end"), int):
        details.append(f"символы: {locator['char_start']}–{locator['char_end']}")
    return f"{document}, {'; '.join(details)}" if details else document


def _extract_matches(
    document: Any,
    *,
    kind: str,
    topic: re.Pattern[str],
    detail: re.Pattern[str],
) -> list[dict[str, Any]]:
    text = str(getattr(document, "text", "") or "")
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in topic.finditer(text):
        start = _boundary_before(text, match.start())
        end = _boundary_after(text, match.end())
        excerpt = _normalize(text[start:end])[:_MAX_EXCERPT_CHARS].strip(" ;")
        if len(excerpt) < 16 or not detail.search(excerpt):
            continue
        normalized = excerpt.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        reference = _chunk_reference(document, excerpt, start, min(end, start + _MAX_EXCERPT_CHARS))
        results.append(
            {
                "kind": kind,
                "text": excerpt,
                "source": reference["document_name"],
                "locator": reference.get("locator", {}),
                "evidence_reference": reference,
                "source_display": _source_display(reference),
            }
        )
        if len(results) >= _MAX_FACTS_PER_KIND:
            break
    return results


def extract_commercial_term_recall(documents: Iterable[Any]) -> list[dict[str, Any]]:
    """Return only source-visible delivery, payment, and acceptance timing facts."""
    found: list[dict[str, Any]] = []
    for document in documents:
        if not _eligible_document(document):
            continue
        found.extend(_extract_matches(document, kind="delivery_period", topic=_DELIVERY_TOPIC, detail=_DELIVERY_TIMING))
        found.extend(_extract_matches(document, kind="payment_terms", topic=_PAYMENT_TOPIC, detail=_PAYMENT_DETAIL))
        found.extend(_extract_matches(document, kind="acceptance_signing_deadline", topic=_ACCEPTANCE_TOPIC, detail=_ACCEPTANCE_TIMING))

    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    counts = {key: 0 for key in _KIND_LABELS}
    for row in found:
        key = (str(row["kind"]), str(row["text"]).casefold())
        if key in seen or counts[row["kind"]] >= _MAX_FACTS_PER_KIND:
            continue
        seen.add(key)
        counts[row["kind"]] += 1
        result.append(row)
    return result


def _highlight(row: dict[str, Any]) -> str:
    label = _KIND_LABELS[str(row["kind"])]
    text = str(row["text"]).rstrip(". ")
    source = str(row.get("source_display") or row.get("source") or "Документы закупки")
    return f"{label}: {text}. Источник: {source}."


def _merge_highlights(existing: list[Any], facts: list[dict[str, Any]]) -> list[str]:
    preferred = [_highlight(row) for row in facts]
    fact_texts = [str(row["text"]).casefold() for row in facts]
    retained: list[str] = []
    for item in existing:
        value = " ".join(str(item or "").split()).strip()
        if not value:
            continue
        lowered = value.casefold()
        if any(text and text in lowered for text in fact_texts):
            continue
        retained.append(value)
    merged: list[str] = []
    seen: set[str] = set()
    for value in [*preferred, *retained]:
        key = " ".join(value.casefold().split())
        if key in seen:
            continue
        seen.add(key)
        merged.append(value)
    return merged[:24]


def _commercial_recall_preliminary(**kwargs: Any) -> dict[str, Any]:
    assert _ORIGINAL_PRELIMINARY is not None
    result = _ORIGINAL_PRELIMINARY(**kwargs)
    metadata = kwargs.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("analysis_mode") != "production_llm_r10_1":
        return result

    facts = extract_commercial_term_recall(kwargs.get("documents") or [])
    if not facts:
        return result

    result = dict(result)
    result["commercial_term_recall"] = facts
    analysis = result.get("decision_useful_analysis")
    if isinstance(analysis, dict):
        analysis = dict(analysis)
        analysis["commercial_term_recall"] = facts
        result["decision_useful_analysis"] = analysis
    result["contract_highlights"] = _merge_highlights(
        list(result.get("contract_highlights") or []), facts
    )
    return result


def install() -> None:
    """Install after the existing decision-usefulness patches."""
    global _INSTALLED, _ORIGINAL_PRELIMINARY
    if _INSTALLED:
        return
    _ORIGINAL_PRELIMINARY = _legacy._build_preliminary_procurement_analysis
    _legacy._build_preliminary_procurement_analysis = _commercial_recall_preliminary
    _INSTALLED = True
