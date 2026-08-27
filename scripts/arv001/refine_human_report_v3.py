#!/usr/bin/env python3
"""Final report-only refinement for the ARV-001 human-facing candidate.

This layer consumes the deterministic v2 report generated from the already
accepted canonical model. It does not re-run analysis and performs no provider,
EIS, database, RAG, Git, or network I/O. Its only purpose is to close concrete
Product Owner presentation defects found in the v2 HTML.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from scripts.arv001 import rework_human_report as _v2
from scripts.arv001.complete_corpus_contract import (
    DEFAULT_REGISTRY_NUMBER,
    AcceptanceBlocked,
    validate_customer_report,
)

_DOCUMENT_SET_RE = re.compile(
    r"<details><summary>Документы комплекта \((\d+)\)</summary><ul>(.*?)</ul></details>",
    re.DOTALL,
)
_SOURCES_SECTION_RE = re.compile(
    r"<section><h2>Источники</h2>(.*?)</section>", re.DOTALL
)
_LIMITATIONS_SECTION_RE = re.compile(
    r"(<section><h2>Ограничения текущего автоматического извлечения</h2><ul>)(.*?)(</ul></section>)",
    re.DOTALL,
)
_CHECKLIST_SECTION_RE = re.compile(
    r"(<section><h2>Контроль перед коммерческим решением</h2><ul>)(.*?)(</ul>)",
    re.DOTALL,
)
_AMBIGUOUS_ACCEPTANCE_RE = re.compile(
    r"<li>Срок при[её]мки:[^<]*со дня подписания Заказчиком документа о при[её]мке\.</li>",
    re.IGNORECASE,
)

_SUBTITLE_OLD = "<p>Отчёт для принятия решения об участии</p>"
_SUBTITLE_NEW = "<p>Предварительный отчёт для подготовки решения об участии</p>"
_BASIS_OLD = "Техническая документация и проект контракта включены в комплект анализа."
_BASIS_NEW = (
    "Техническая документация и проект контракта присутствуют в комплекте; "
    "существенные условия, не извлечённые автоматически, перечислены в ограничениях."
)
_APPLICATION_CHECK = (
    "Проверить требования к составу заявки и участнику по Приложению 3 закупочной документации."
)
_ACCEPTANCE_CHECK = (
    "Сверить формулировку срока и процедуры приёмки непосредственно с проектом контракта."
)
_ACCEPTANCE_LIMITATION = (
    "Автоматическое извлечение срока приёмки дало внутренне неоднозначную формулировку; "
    "срок и процедуру приёмки нужно проверить по проекту контракта."
)
_ACCEPTANCE_REPLACEMENT = (
    "<li>Срок приёмки: автоматическое извлечение содержит внутренне неоднозначную "
    "формулировку; требуется ручная сверка с проектом контракта.</li>"
)


def _replace_once(value: str, old: str, new: str) -> str:
    if old not in value:
        return value
    return value.replace(old, new, 1)


def _append_list_item(
    rendered_html: str, pattern: re.Pattern[str], text: str
) -> str:
    match = pattern.search(rendered_html)
    if match is None:
        raise AcceptanceBlocked("customer_report_expected_section_missing")
    if text in match.group(2):
        return rendered_html
    replacement = match.group(1) + match.group(2) + f"<li>{_v2._escape(text)}</li>" + match.group(3)
    return rendered_html[: match.start()] + replacement + rendered_html[match.end() :]


def _expand_sources(rendered_html: str) -> str:
    documents = _DOCUMENT_SET_RE.search(rendered_html)
    sources = _SOURCES_SECTION_RE.search(rendered_html)
    if documents is None or sources is None:
        raise AcceptanceBlocked("customer_report_document_sources_missing")

    count = documents.group(1)
    document_items = documents.group(2)
    existing = sources.group(1)
    existing_list = re.search(r"<ul>(.*?)</ul>", existing, re.DOTALL)
    point_items = existing_list.group(1) if existing_list is not None else ""

    section = (
        "<section><h2>Источники</h2>"
        f"<p>Комплект документов, использованный для отчёта ({count}):</p>"
        f"<ul>{document_items}</ul>"
    )
    if point_items.strip():
        section += (
            "<p>Подтверждённые ссылки на конкретные факты:</p>"
            f"<ul>{point_items}</ul>"
        )
    section += "</section>"
    return rendered_html[: sources.start()] + section + rendered_html[sources.end() :]


def refine_report_v3(
    model: dict[str, Any], *, expected_registry_number: str
) -> str:
    """Return a v3 customer candidate without mutating accepted canonical data."""

    before = _v2._canonical_bytes(model)
    rendered = _v2.rework_canonical_report(
        model, expected_registry_number=expected_registry_number
    )
    if _v2._canonical_bytes(model) != before:
        raise AcceptanceBlocked("canonical_report_mutated_before_v3_refinement")

    rendered = _replace_once(rendered, _SUBTITLE_OLD, _SUBTITLE_NEW)
    rendered = _replace_once(rendered, _BASIS_OLD, _BASIS_NEW)

    ambiguous_acceptance = bool(_AMBIGUOUS_ACCEPTANCE_RE.search(rendered))
    if ambiguous_acceptance:
        rendered = _AMBIGUOUS_ACCEPTANCE_RE.sub(
            _ACCEPTANCE_REPLACEMENT, rendered, count=1
        )
        rendered = _append_list_item(
            rendered, _LIMITATIONS_SECTION_RE, _ACCEPTANCE_LIMITATION
        )

    rendered = _append_list_item(rendered, _CHECKLIST_SECTION_RE, _APPLICATION_CHECK)
    if ambiguous_acceptance:
        rendered = _append_list_item(rendered, _CHECKLIST_SECTION_RE, _ACCEPTANCE_CHECK)

    rendered = _expand_sources(rendered)

    validate_customer_report(rendered, expected_registry_number)
    _v2._validate_customer_rework(rendered)
    if _SUBTITLE_NEW not in rendered:
        raise AcceptanceBlocked("customer_report_preliminary_scope_missing")
    if _APPLICATION_CHECK not in rendered:
        raise AcceptanceBlocked("customer_report_application_check_missing")
    if "Комплект документов, использованный для отчёта" not in rendered:
        raise AcceptanceBlocked("customer_report_source_set_missing")
    if ambiguous_acceptance and _AMBIGUOUS_ACCEPTANCE_RE.search(rendered):
        raise AcceptanceBlocked("customer_report_ambiguous_acceptance_not_removed")
    if _v2._canonical_bytes(model) != before:
        raise AcceptanceBlocked("canonical_report_mutated_during_v3_refinement")
    return rendered


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refine the accepted ARV-001 report candidate to v3 without rerunning analysis."
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

    model, input_file_sha256 = _v2._read_canonical_report(input_path)
    model_hash_before = _v2._sha256_bytes(_v2._canonical_bytes(model))
    refined = refine_report_v3(
        model, expected_registry_number=args.expected_registry_number
    )
    if _v2._sha256_bytes(_v2._canonical_bytes(model)) != model_hash_before:
        raise AcceptanceBlocked("canonical_report_mutated")
    _v2._atomic_write_new(output_path, refined)

    print(
        json.dumps(
            {
                "status": "report_rework_v3_candidate",
                "task": "ARV-001",
                "canonical_input_sha256": input_file_sha256,
                "reworked_report_sha256": _v2._sha256_bytes(refined.encode("utf-8")),
                "technical_quality": "PASSED",
                "quality_evidence": "EXISTS",
                "product_owner": "REJECTED",
                "required_action": "REPORT_REWORK_REQUIRED",
                "independent_review": "NOT_AUTHORIZED",
                "freeze": "NOT_ALLOWED",
                "provider_calls_performed": False,
                "eis_requests_performed": False,
                "quality_acceptance_rerun": False,
                "accepted_evidence_mutated": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
