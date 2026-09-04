"""Focused follow-up hardening for PILOT-001-D04.

This module is deliberately small: it corrects category resolution and keeps
fallback labels evidence-neutral without changing the underlying provenance or
external-action boundary.
"""

from __future__ import annotations

import re
from typing import Any

from src.modules.tender_operator_agent_demo import grounded_fallback_patch as _grounded

_INSTALLED = False
_ORIGINAL_PRELIMINARY: Any = None
_ORIGINAL_SANITIZE_ECONOMICS: Any = None
_ORIGINAL_INSUFFICIENT: Any = None


def _strict_category(procurement_kind: str | None) -> str:
    kind = (procurement_kind or "").strip().lower()
    if kind == "goods":
        return "GOODS"
    if kind == "services":
        return "SERVICES"
    if kind == "works":
        return "WORKS"
    # Mixed and specialized legacy labels are not safe substitutes for one of
    # the three canonical categories unless the primary scope is explicit.
    return "UNKNOWN"


def _title_primary_scope(metadata: dict[str, Any]) -> str | None:
    title = str(metadata.get("tender_title") or "").lower()
    if re.search(r"\b(?:выполнение|проведение)\s+работ\b|\bработы\s+по\b", title):
        return "works"
    if re.search(r"\b(?:оказание|предоставление)\s+услуг\b|\bуслуги\s+по\b", title):
        return "services"
    if re.search(r"\bпоставка\b|\bпоставку\b|\bприобретение\s+товар", title):
        return "goods"
    return None


def _preliminary_with_explicit_scope(**kwargs: Any) -> dict[str, Any]:
    result = dict(_ORIGINAL_PRELIMINARY(**kwargs))
    existing_kind = str(result.get("procurement_kind") or "").strip().lower()
    explicit = _title_primary_scope(kwargs.get("metadata") or {})
    # D07 introduces a provenance-backed semantic scope.  Title heuristics are
    # a compatibility fallback only: they must never overwrite a resolved
    # canonical category such as rental/mixed/goods/services/works.
    if explicit and existing_kind in {"", "unknown", "unresolved", "generic"}:
        result["procurement_kind"] = explicit
        result["grounded_fallback_category"] = _strict_category(explicit)
    else:
        result["grounded_fallback_category"] = _strict_category(result.get("procurement_kind"))
    return result


def _evidence_neutral_insufficient(theme_or_label: str) -> str:
    if theme_or_label == "drums":
        return (
            "INSUFFICIENT_EVIDENCE: специальное условие упаковки/отгрузки — "
            "первичные документы не подтверждают это условие."
        )
    return _ORIGINAL_INSUFFICIENT(theme_or_label)


def _sanitize_economics_preserving_grounded_cable_label(
    payload: dict[str, Any], *, corpus: str
) -> dict[str, Any]:
    sanitized = _ORIGINAL_SANITIZE_ECONOMICS(payload, corpus=corpus)
    if re.search(r"\b(?:кабел|провод)\w*", corpus, re.IGNORECASE):
        for metric in sanitized.get("metrics", []):
            if not isinstance(metric, dict):
                continue
            if metric.get("label") == "Арифметический ориентир НМЦК на единицу «м»":
                metric["label"] = "Ориентир по НМЦК на метр"
    return sanitized


def install() -> None:
    """Install the D04 follow-up exactly once."""
    global _INSTALLED, _ORIGINAL_PRELIMINARY, _ORIGINAL_SANITIZE_ECONOMICS, _ORIGINAL_INSUFFICIENT
    if _INSTALLED:
        return
    _ORIGINAL_PRELIMINARY = _grounded._build_preliminary_procurement_analysis
    _ORIGINAL_SANITIZE_ECONOMICS = _grounded._sanitize_economics
    _ORIGINAL_INSUFFICIENT = _grounded._insufficient
    _grounded._category = _strict_category
    _grounded._insufficient = _evidence_neutral_insufficient
    _grounded._sanitize_economics = _sanitize_economics_preserving_grounded_cable_label
    _grounded._build_preliminary_procurement_analysis = _preliminary_with_explicit_scope

    # The legacy service was already pointed at the grounded wrapper. Replace it
    # with this final wrapper so an unresolved legacy classification may use an
    # obvious title, while a resolved D07 semantic scope remains authoritative.
    _grounded._legacy._build_preliminary_procurement_analysis = _preliminary_with_explicit_scope
    _INSTALLED = True
