"""Second-pass decision-useful extraction for material liability limits."""

from __future__ import annotations

import re
from typing import Any, Iterable

from src.modules.tender_operator_agent_demo.decision_useful_extraction import (
    extract_decision_useful_analysis as _base_extract,
)

_CAP_MARKER = re.compile(
    r"(?:общ(?:ая|ий|ее)|совокупн\w*)[^.\n]{0,220}?"
    r"(?:штраф\w*|пен(?:я|и|ей)|неустойк\w*|ответственност\w*)[^.\n]{0,220}?"
    r"(?:не\s+может\s+превышать|не\s+превышает|не\s+более|ограничива\w*)",
    re.IGNORECASE,
)


def _public_source(document: Any) -> tuple[str, str]:
    role = str(getattr(document, "role", "") or "").lower()
    name = str(getattr(document, "display_name", "") or "").lower()
    haystack = f"{role} {name}"
    if any(token in haystack for token in ("contract_performance_security", "performance_security", "обеспечени", "реквизиты")):
        return "security", "Обеспечение исполнения контракта"
    if any(token in haystack for token in ("contract_draft", "draft_contract", "контракт", "договор")):
        return "contract", "Проект контракта"
    return "other", "Документ закупки"


def _normalize(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split()).strip()


def _cap_rows(documents: Iterable[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for document in documents:
        kind, source = _public_source(document)
        if kind not in {"contract", "security"}:
            continue
        text = str(getattr(document, "text", "") or "")
        for match in _CAP_MARKER.finditer(text):
            start = max(
                text.rfind("\n", max(0, match.start() - 420), match.start()),
                text.rfind(". ", max(0, match.start() - 420), match.start()),
            )
            start = start + 2 if start >= 0 and text[start : start + 2] == ". " else (start + 1 if start >= 0 else max(0, match.start() - 420))
            candidates = [
                value for value in (
                    text.find("\n", match.end(), min(len(text), match.end() + 700)),
                    text.find(". ", match.end(), min(len(text), match.end() + 700)),
                ) if value >= 0
            ]
            end = (min(candidates) + 1) if candidates else min(len(text), match.end() + 700)
            excerpt = _normalize(text[start:end])[:1100].strip(" ;")
            key = excerpt.casefold()
            if not excerpt or key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "text": excerpt,
                    "source": source,
                    "locator": {"char_start": start, "char_end": min(end, start + 1100)},
                }
            )
            if len(rows) >= 4:
                return rows
    return rows


def extract_decision_useful_analysis(documents: Iterable[Any]) -> dict[str, Any]:
    document_list = list(documents)
    result = _base_extract(document_list)
    contract = result.setdefault("contract", {})
    cap_rows = _cap_rows(document_list)
    contract["liability_cap"] = cap_rows
    contract["liability_cap_status"] = "found" if cap_rows else "not_found_in_processed_contract_text"
    return result
