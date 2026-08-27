"""Second-pass decision-useful extraction for material liability/security terms."""

from __future__ import annotations

import re
from typing import Any, Iterable

from src.modules.tender_operator_agent_demo.decision_useful_extraction import (
    _MAX_CONTRACT_CLAUSES,
    _SECURITY_MARKERS,
    _clauses,
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
    if any(
        token in haystack
        for token in (
            "contract_performance_security",
            "performance_security",
            "обеспечени",
            "реквизиты",
        )
    ):
        return "security", "Обеспечение исполнения контракта"
    if any(
        token in haystack
        for token in ("contract_draft", "draft_contract", "контракт", "договор")
    ):
        return "contract", "Проект контракта"
    if any(token in haystack for token in ("notice", "notification", "извещ")):
        return "notice", "Извещение о закупке"
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
            start = (
                start + 2
                if start >= 0 and text[start : start + 2] == ". "
                else (start + 1 if start >= 0 else max(0, match.start() - 420))
            )
            candidates = [
                value
                for value in (
                    text.find(
                        "\n", match.end(), min(len(text), match.end() + 700)
                    ),
                    text.find(
                        ". ", match.end(), min(len(text), match.end() + 700)
                    ),
                )
                if value >= 0
            ]
            end = (
                (min(candidates) + 1)
                if candidates
                else min(len(text), match.end() + 700)
            )
            excerpt = _normalize(text[start:end])[:1100].strip(" ;")
            key = excerpt.casefold()
            if not excerpt or key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "text": excerpt,
                    "source": source,
                    "locator": {
                        "char_start": start,
                        "char_end": min(end, start + 1100),
                    },
                }
            )
            if len(rows) >= 4:
                return rows
    return rows


def _notice_security_rows(documents: Iterable[Any]) -> list[dict[str, Any]]:
    """Recover a size/form clause when EIS notice carries it outside the draft."""

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for document in documents:
        kind, source = _public_source(document)
        if kind != "notice":
            continue
        text = str(getattr(document, "text", "") or "")
        for row in _clauses(
            text,
            _SECURITY_MARKERS,
            source=source,
            limit=_MAX_CONTRACT_CLAUSES,
            require_specificity=True,
        ):
            key = str(row.get("text") or "").casefold()
            if key and key not in seen:
                seen.add(key)
                rows.append(row)
    return rows


def extract_decision_useful_analysis(documents: Iterable[Any]) -> dict[str, Any]:
    document_list = list(documents)
    result = _base_extract(document_list)
    contract = result.setdefault("contract", {})

    existing_security = list(contract.get("security") or [])
    security_seen = {
        str(row.get("text") or "").casefold()
        for row in existing_security
        if isinstance(row, dict)
    }
    for row in _notice_security_rows(document_list):
        key = str(row.get("text") or "").casefold()
        if key and key not in security_seen:
            security_seen.add(key)
            existing_security.append(row)
    contract["security"] = existing_security[:_MAX_CONTRACT_CLAUSES]

    cap_rows = _cap_rows(document_list)
    contract["liability_cap"] = cap_rows
    contract["liability_cap_status"] = (
        "found" if cap_rows else "not_found_in_processed_contract_text"
    )
    return result
