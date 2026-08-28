"""Fail closed when a decision-useful analysis loses material terms in HTML."""

from __future__ import annotations

import html as html_lib
import re
from typing import Any

from scripts.arv001.complete_corpus_contract import AcceptanceBlocked

_REQUIRED_CONTRACT_GROUPS = ("payment", "security", "acceptance", "liability")
_OPTIONAL_CONTRACT_GROUPS = ("termination",)


def _plain_text(rendered: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", rendered)
    return " ".join(html_lib.unescape(without_tags).split()).casefold()


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in (value or []) if isinstance(row, dict) and row.get("text")]


def _require_excerpt(plain: str, excerpt: str, code: str) -> None:
    if _normalized(excerpt) not in plain:
        raise AcceptanceBlocked(code)


def validate_rendered_material_terms(rendered: str, analysis: dict[str, Any]) -> dict[str, Any]:
    """Prove that extracted decision-useful material survived customer rendering.

    The extraction gate establishes semantic sufficiency. This validator checks
    the second half of the contract: source-backed terms accepted by that gate
    must still be visible in the final customer HTML. It does not infer or
    synthesize missing facts.
    """

    plain = _plain_text(rendered)
    technical = analysis.get("technical") if isinstance(analysis.get("technical"), dict) else {}
    contract = analysis.get("contract") if isinstance(analysis.get("contract"), dict) else {}

    standards = [str(value) for value in technical.get("standards") or [] if value]
    if not standards:
        raise AcceptanceBlocked("decision_useful_rendered_exact_standard_missing")
    for standard in standards:
        _require_excerpt(plain, standard, "decision_useful_rendered_exact_standard_missing")

    technical_rows = _rows(technical.get("specific_clauses"))
    if not technical_rows:
        raise AcceptanceBlocked("decision_useful_rendered_technical_detail_missing")
    for row in technical_rows:
        _require_excerpt(
            plain,
            str(row["text"]),
            "decision_useful_rendered_technical_detail_missing",
        )

    visible_counts: dict[str, int] = {}
    for group in _REQUIRED_CONTRACT_GROUPS:
        rows = _rows(contract.get(group))[:6]
        if not rows:
            raise AcceptanceBlocked(f"decision_useful_rendered_{group}_missing")
        for row in rows:
            _require_excerpt(
                plain,
                str(row["text"]),
                f"decision_useful_rendered_{group}_missing",
            )
        visible_counts[group] = len(rows)

    for group in _OPTIONAL_CONTRACT_GROUPS:
        rows = _rows(contract.get(group))[:6]
        for row in rows:
            _require_excerpt(
                plain,
                str(row["text"]),
                f"decision_useful_rendered_{group}_missing",
            )
        visible_counts[group] = len(rows)

    cap_status = str(contract.get("liability_cap_status") or "not_checked")
    cap_rows = _rows(contract.get("liability_cap"))
    if cap_status == "found":
        if not cap_rows:
            raise AcceptanceBlocked("decision_useful_rendered_liability_cap_missing")
        for row in cap_rows:
            _require_excerpt(
                plain,
                str(row["text"]),
                "decision_useful_rendered_liability_cap_missing",
            )
    elif cap_status == "not_found_in_processed_contract_text":
        if "ограничение общей суммы штрафов не найдено" not in plain:
            raise AcceptanceBlocked("decision_useful_rendered_liability_cap_status_missing")
    else:
        raise AcceptanceBlocked("decision_useful_rendered_liability_cap_not_assessed")

    application_rows = _rows(analysis.get("application_requirements"))
    if not application_rows:
        raise AcceptanceBlocked("decision_useful_rendered_application_requirements_missing")
    for row in application_rows:
        _require_excerpt(
            plain,
            str(row["text"]),
            "decision_useful_rendered_application_requirements_missing",
        )

    return {
        "status": "PASS",
        "exact_standard_count": len(standards),
        "technical_detail_count": len(technical_rows),
        "contract_visible_counts": visible_counts,
        "liability_cap_status": cap_status,
        "application_requirement_count": len(application_rows),
    }
