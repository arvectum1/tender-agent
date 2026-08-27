"""Decision-useful, source-bound extraction for customer procurement reports.

The existing R10.1 controlled LLM path is deliberately conservative, but its
legacy compatibility layer historically collapsed material contract clauses to
presence flags (for example, "the contract contains payment terms").  This
module preserves concrete source clauses from already-extracted procurement
documents so the customer report can show the actual commercial mechanics.

No inference is performed here.  Returned values are normalized excerpts from
source text plus deterministic source/offset locators.  If a specific term is
not present in the processed text, the corresponding list remains empty.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

_MAX_CLAUSE_CHARS = 1100
_MAX_TECHNICAL_CLAUSES = 10
_MAX_CONTRACT_CLAUSES = 8
_MAX_APPLICATION_CLAUSES = 12

_GOST_RE = re.compile(
    r"\bГОСТ(?:\s+Р)?\s+\d[\d.\-/–—]*(?:-\d{2,4})?\b",
    re.IGNORECASE,
)
_TR_TS_RE = re.compile(r"\bТР\s*ТС\s*\d{1,4}/\d{4}\b", re.IGNORECASE)
_TU_RE = re.compile(r"\bТУ\s+\d[\d.\-/–—]+\b", re.IGNORECASE)

_TECHNICAL_MARKERS = re.compile(
    r"\b(?:ГОСТ|ТР\s*ТС|ТУ|класс|марка|сорт|тип|вид|зимн\w*|летн\w*|"
    r"арктич\w*|экологическ\w*|евро\s*[-–]?\s*\d+|температур\w*|"
    r"цетанов\w*|содержани\w*\s+сер\w*|плотност\w*|фракц\w*|"
    r"вспышк\w*|вязкост\w*)\b",
    re.IGNORECASE,
)
_PAYMENT_MARKERS = re.compile(
    r"\b(?:оплат\w*|аванс\w*|предоплат\w*|постоплат\w*|расч[её]т\w*)\b",
    re.IGNORECASE,
)
_SECURITY_MARKERS = re.compile(
    r"\bобеспечени\w*\s+исполнени\w*\s+(?:контракт\w*|договор\w*)\b",
    re.IGNORECASE,
)
_ACCEPTANCE_MARKERS = re.compile(
    r"\b(?:при[её]мк\w*|документ\w*\s+о\s+при[её]мк\w*|акт\w*\s+при[её]мк\w*)\b",
    re.IGNORECASE,
)
_LIABILITY_MARKERS = re.compile(
    r"\b(?:штраф\w*|пен(?:я|и|ей|ею)|неустойк\w*|ответственност\w*)\b",
    re.IGNORECASE,
)
_TERMINATION_MARKERS = re.compile(
    r"\b(?:односторонн\w*\s+отказ\w*|расторжен\w*|отказ\w*\s+от\s+исполнени\w*)\b",
    re.IGNORECASE,
)
_APPLICATION_MARKERS = re.compile(
    r"\b(?:заявк\w*\s+(?:должн\w*\s+)?содерж\w*|состав\w*\s+заявк\w*|"
    r"предостав\w*\s+(?:в\s+составе\s+)?заявк\w*|декларац\w*|лицензи\w*|"
    r"свидетельств\w*|сертификат\w*|выписк\w*|СРО|аккредитац\w*)\b",
    re.IGNORECASE,
)
_SPECIFICITY_RE = re.compile(
    r"(?:\d|%|руб\w*|дн(?:ей|я)|рабоч\w*|календарн\w*|аванс\w*|"
    r"постоплат\w*|банковск\w*|независим\w*\s+гарант\w*|ключев\w*\s+ставк\w*)",
    re.IGNORECASE,
)


def _normalize(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split()).strip()


def _public_source(document: Any) -> tuple[str, str]:
    role = str(getattr(document, "role", "") or "").strip().lower()
    name = str(getattr(document, "display_name", "") or "").strip().lower()
    haystack = f"{role} {name}"
    if any(token in haystack for token in ("application", "заявк", "состав заявки")):
        return "application", "Требования к составу заявки"
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
    if any(token in haystack for token in ("contract_draft", "draft_contract", "контракт", "договор")):
        return "contract", "Проект контракта"
    if any(
        token in haystack
        for token in (
            "technical_spec",
            "technical specification",
            "техническ",
            "описание объекта",
            "спецификац",
        )
    ):
        return "technical", "Техническое задание"
    if any(token in haystack for token in ("price_justification", "nmck", "нмцк")):
        return "price", "Обоснование НМЦК"
    if any(token in haystack for token in ("notice", "notification", "извещ")):
        return "notice", "Извещение о закупке"
    return "other", "Документ закупки"


def _boundary_before(text: str, start: int, radius: int = 520) -> int:
    floor = max(0, start - radius)
    candidates = [
        text.rfind("\n", floor, start),
        text.rfind(". ", floor, start),
        text.rfind("; ", floor, start),
    ]
    boundary = max(candidates)
    return boundary + (2 if boundary >= 0 and text[boundary : boundary + 2] in {". ", "; "} else 1) if boundary >= 0 else floor


def _boundary_after(text: str, end: int, radius: int = 900) -> int:
    ceiling = min(len(text), end + radius)
    candidates = [value for value in (
        text.find("\n", end, ceiling),
        text.find(". ", end, ceiling),
        text.find("; ", end, ceiling),
    ) if value >= 0]
    if not candidates:
        return ceiling
    boundary = min(candidates)
    return boundary + 1


def _clauses(
    text: str,
    marker: re.Pattern[str],
    *,
    source: str,
    limit: int,
    require_specificity: bool = False,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in marker.finditer(text):
        start = _boundary_before(text, match.start())
        end = _boundary_after(text, match.end())
        excerpt = _normalize(text[start:end])[:_MAX_CLAUSE_CHARS].strip(" ;")
        if len(excerpt) < 12:
            continue
        if require_specificity and not _SPECIFICITY_RE.search(excerpt):
            continue
        key = excerpt.casefold()
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "text": excerpt,
                "source": source,
                "locator": {"char_start": start, "char_end": min(end, start + _MAX_CLAUSE_CHARS)},
            }
        )
        if len(results) >= limit:
            break
    return results


def _standards(texts: Iterable[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for pattern in (_GOST_RE, _TR_TS_RE, _TU_RE):
            for match in pattern.finditer(text):
                value = _normalize(match.group(0))
                key = value.casefold()
                if key not in seen:
                    seen.add(key)
                    values.append(value)
    return values


def _technical_specific_clauses(text: str, *, source: str) -> list[dict[str, Any]]:
    rows = _clauses(
        text,
        _TECHNICAL_MARKERS,
        source=source,
        limit=_MAX_TECHNICAL_CLAUSES * 2,
    )
    specific: list[dict[str, Any]] = []
    for row in rows:
        value = str(row["text"])
        if not (_SPECIFICITY_RE.search(value) or _GOST_RE.search(value) or _TR_TS_RE.search(value) or _TU_RE.search(value)):
            continue
        specific.append(row)
        if len(specific) >= _MAX_TECHNICAL_CLAUSES:
            break
    return specific


def extract_decision_useful_analysis(documents: Iterable[Any]) -> dict[str, Any]:
    """Extract exact material clauses from the already-processed document set."""

    technical_rows: list[dict[str, Any]] = []
    application_rows: list[dict[str, Any]] = []
    contract_groups: dict[str, list[dict[str, Any]]] = {
        "payment": [],
        "security": [],
        "acceptance": [],
        "liability": [],
        "termination": [],
    }
    standard_inputs: list[str] = []

    for document in documents:
        text = str(getattr(document, "text", "") or "")
        if not text.strip():
            continue
        kind, source = _public_source(document)
        if kind == "technical":
            standard_inputs.append(text)
            technical_rows.extend(_technical_specific_clauses(text, source=source))
        if kind in {"contract", "security"}:
            contract_groups["payment"].extend(
                _clauses(text, _PAYMENT_MARKERS, source=source, limit=_MAX_CONTRACT_CLAUSES, require_specificity=True)
            )
            contract_groups["security"].extend(
                _clauses(text, _SECURITY_MARKERS, source=source, limit=_MAX_CONTRACT_CLAUSES, require_specificity=True)
            )
            contract_groups["acceptance"].extend(
                _clauses(text, _ACCEPTANCE_MARKERS, source=source, limit=_MAX_CONTRACT_CLAUSES, require_specificity=True)
            )
            contract_groups["liability"].extend(
                _clauses(text, _LIABILITY_MARKERS, source=source, limit=_MAX_CONTRACT_CLAUSES, require_specificity=True)
            )
            contract_groups["termination"].extend(
                _clauses(text, _TERMINATION_MARKERS, source=source, limit=_MAX_CONTRACT_CLAUSES)
            )
        if kind == "application":
            application_rows.extend(
                _clauses(text, _APPLICATION_MARKERS, source=source, limit=_MAX_APPLICATION_CLAUSES)
            )

    def dedupe(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            key = (str(row.get("source")), str(row.get("text")).casefold())
            if key in seen:
                continue
            seen.add(key)
            result.append(row)
            if len(result) >= limit:
                break
        return result

    return {
        "technical": {
            "standards": _standards(standard_inputs),
            "specific_clauses": dedupe(technical_rows, _MAX_TECHNICAL_CLAUSES),
        },
        "contract": {
            key: dedupe(value, _MAX_CONTRACT_CLAUSES)
            for key, value in contract_groups.items()
        },
        "application_requirements": dedupe(application_rows, _MAX_APPLICATION_CLAUSES),
    }


def material_detail_count(value: dict[str, Any]) -> int:
    """Return a stable count used by report/quality tests."""

    technical = value.get("technical") if isinstance(value.get("technical"), dict) else {}
    contract = value.get("contract") if isinstance(value.get("contract"), dict) else {}
    count = len(technical.get("standards") or []) + len(technical.get("specific_clauses") or [])
    count += sum(len(contract.get(key) or []) for key in ("payment", "security", "acceptance", "liability", "termination"))
    count += len(value.get("application_requirements") or [])
    return count
