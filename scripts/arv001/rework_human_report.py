#!/usr/bin/env python3
"""Rework the accepted ARV-001 customer report without rerunning analysis.

This tool is intentionally report-only. It reads an already-persisted R10.1
``canonical_report.json``, renders it through the existing sanitized customer
renderer, validates the accepted procurement content, and adds the current
human-governance state. It performs no provider, EIS, database, or network I/O.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from scripts.arv001.complete_corpus_contract import (
    DEFAULT_REGISTRY_NUMBER,
    AcceptanceBlocked,
    validate_customer_report,
)
from src.modules.tender_operator_agent_demo.upload_service import (
    _is_r10_1_model,
    _render_customer_report_html,
)

_GOVERNANCE_MARKER = 'id="arv001-governance"'
_DECISION_MARKER = '<section class="decision"><h2>Решение:'
_RECOMMENDATION_MARKER = (
    '<section class="decision"><h2>Рекомендация по закупке:'
)
_FORBIDDEN_READINESS_PHRASES = (
    "ready for independent review",
    "approved for independent review",
    "accepted for independent review",
    "independent review authorized",
    "готов к независимой проверке",
    "независимая проверка разрешена",
)

_GOVERNANCE_BLOCK = """<section id="arv001-governance">
<h2>Статус ARV-001 до повторного решения Product Owner</h2>
<ul>
<li><strong>Техническое качество:</strong> PASSED</li>
<li><strong>Quality evidence:</strong> EXISTS</li>
<li><strong>Product Owner:</strong> REJECTED — требуется переработка human-facing report</li>
<li><strong>Требуемое действие:</strong> REPORT_REWORK_REQUIRED</li>
<li><strong>Independent review:</strong> NOT_AUTHORIZED</li>
<li><strong>Freeze:</strong> NOT_ALLOWED</li>
<li><strong>P8.05 / внешний источник:</strong> BLOCKED_EXTERNAL_SOURCE</li>
</ul>
<p>Ограничение P8.05 относится к доступности внешнего источника и не отменяет технический результат PASSED.</p>
<p>Этот переработанный отчёт является кандидатом на повторное рассмотрение Product Owner. Его формирование само по себе не меняет статус Product Owner и не разрешает independent review.</p>
</section>"""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _read_canonical_report(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AcceptanceBlocked("canonical_report_unreadable") from exc
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceBlocked("canonical_report_invalid_json") from exc
    if not isinstance(value, dict):
        raise AcceptanceBlocked("canonical_report_invalid_shape")
    if not _is_r10_1_model(value):
        raise AcceptanceBlocked("canonical_report_not_r10_1")
    return value, _sha256_bytes(raw)


def _inject_governance(rendered_html: str) -> str:
    if _GOVERNANCE_MARKER in rendered_html:
        raise AcceptanceBlocked("arv001_governance_already_present")
    if rendered_html.count("<main>") != 1:
        raise AcceptanceBlocked("customer_report_main_marker_invalid")
    if rendered_html.count(_DECISION_MARKER) != 1:
        raise AcceptanceBlocked("customer_report_decision_marker_invalid")

    reworked = rendered_html.replace(
        "<main>", f"<main>\n{_GOVERNANCE_BLOCK}", 1
    ).replace(_DECISION_MARKER, _RECOMMENDATION_MARKER, 1)
    return reworked


def _validate_governance(reworked_html: str) -> None:
    required = (
        "Техническое качество:</strong> PASSED",
        "Quality evidence:</strong> EXISTS",
        "Product Owner:</strong> REJECTED",
        "REPORT_REWORK_REQUIRED",
        "Independent review:</strong> NOT_AUTHORIZED",
        "Freeze:</strong> NOT_ALLOWED",
        "P8.05 / внешний источник:</strong> BLOCKED_EXTERNAL_SOURCE",
        "Рекомендация по закупке:",
    )
    missing = [value for value in required if value not in reworked_html]
    if missing:
        raise AcceptanceBlocked("arv001_governance_required_content_missing")

    lowered = reworked_html.lower()
    if any(value in lowered for value in _FORBIDDEN_READINESS_PHRASES):
        raise AcceptanceBlocked("arv001_independent_review_readiness_forbidden")
    if _DECISION_MARKER in reworked_html:
        raise AcceptanceBlocked("arv001_ambiguous_decision_label_present")


def rework_canonical_report(
    model: dict[str, Any], *, expected_registry_number: str
) -> str:
    """Return the report-rework candidate without mutating canonical evidence."""

    if not isinstance(model, dict) or not _is_r10_1_model(model):
        raise AcceptanceBlocked("canonical_report_not_r10_1")
    before = _canonical_bytes(model)
    rendered = _render_customer_report_html(model)
    after = _canonical_bytes(model)
    if before != after:
        raise AcceptanceBlocked("canonical_report_mutated_during_render")

    validate_customer_report(rendered, expected_registry_number)
    reworked = _inject_governance(rendered)
    validate_customer_report(reworked, expected_registry_number)
    _validate_governance(reworked)
    return reworked


def _atomic_write_new(path: Path, content: str) -> None:
    destination = path.expanduser().resolve()
    if destination.exists():
        raise AcceptanceBlocked("reworked_report_output_already_exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".partial", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rework an accepted ARV-001 canonical report without rerunning analysis."
    )
    parser.add_argument("--canonical-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--expected-registry-number", default=DEFAULT_REGISTRY_NUMBER
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    input_path = args.canonical_output.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    if input_path == output_path:
        raise AcceptanceBlocked("reworked_report_output_equals_input")

    model, input_file_sha256 = _read_canonical_report(input_path)
    model_hash_before = _sha256_bytes(_canonical_bytes(model))
    reworked = rework_canonical_report(
        model, expected_registry_number=args.expected_registry_number
    )
    if _sha256_bytes(_canonical_bytes(model)) != model_hash_before:
        raise AcceptanceBlocked("canonical_report_mutated")
    _atomic_write_new(output_path, reworked)

    print(
        json.dumps(
            {
                "status": "report_rework_candidate",
                "task": "ARV-001",
                "canonical_input_sha256": input_file_sha256,
                "reworked_report_sha256": _sha256_bytes(
                    reworked.encode("utf-8")
                ),
                "technical_quality": "PASSED",
                "quality_evidence": "EXISTS",
                "product_owner": "REJECTED",
                "required_action": "REPORT_REWORK_REQUIRED",
                "independent_review": "NOT_AUTHORIZED",
                "freeze": "NOT_ALLOWED",
                "external_source_checkpoint": "P8.05",
                "external_source_status": "BLOCKED_EXTERNAL_SOURCE",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
