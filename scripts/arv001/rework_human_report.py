#!/usr/bin/env python3
"""Rework the accepted ARV-001 customer report without rerunning analysis.

This tool is intentionally report-only. It reads an already-persisted R10.1
``canonical_report.json``, renders it through the existing sanitized customer
renderer, validates the accepted procurement content, and turns that rendering
into a clearer customer-facing decision report. Internal ARV-001 governance is
kept in CLI/sidecar status only and is never inserted into the customer HTML.
The tool performs no provider, EIS, database, or network I/O.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from scripts.arv001.complete_corpus_contract import (
    DEFAULT_REGISTRY_NUMBER,
    AcceptanceBlocked,
    validate_customer_report,
)
from src.modules.tender_operator_agent_demo import report_model as _report_model
from src.modules.tender_operator_agent_demo.customer_report_contract import (
    build_customer_detail_projection,
)
from src.modules.tender_operator_agent_demo.report_model import (
    build_customer_report_projection,
)
from src.modules.tender_operator_agent_demo.upload_service import (
    _is_r10_1_model,
    _render_customer_report_html,
)

_DECISION_SECTION_RE = re.compile(
    r'<section class="decision">.*?</section>', re.DOTALL
)
_APPLICATION_SECTION_RE = re.compile(
    r'<section><h2>Требования к заявке и участнику</h2>.*?</section>', re.DOTALL
)
_QUESTIONS_SECTION_RE = re.compile(
    r'<section><h2>Вопросы для уточнения</h2>.*?</section>', re.DOTALL
)
_COMMERCIAL_SECTION_MARKER = "<section><h2>Коммерческие предложения</h2>"
_RAW_SOURCE_FILE_RE = re.compile(
    r"\b[A-Za-z][A-Za-z0-9_.-]*[0-9A-Fa-f]{16,}[A-Za-z0-9_.-]*\."
    r"(?:xml|json|txt|bin)\b",
    re.IGNORECASE,
)
_FORBIDDEN_READINESS_PHRASES = (
    "ready for independent review",
    "approved for independent review",
    "accepted for independent review",
    "independent review authorized",
    "готов к независимой проверке",
    "независимая проверка разрешена",
)
_INTERNAL_CUSTOMER_FORBIDDEN = (
    "Product Owner",
    "REPORT_REWORK_REQUIRED",
    "NOT_AUTHORIZED",
    "NOT_ALLOWED",
    "BLOCKED_EXTERNAL_SOURCE",
    "P8.05",
    "Quality evidence",
)
_GENERIC_PAYMENT_MARKER = "проект контракта содержит условия оплаты"


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


def _escape(value: Any) -> str:
    return html.escape(str(value or "").strip())


def _bullets(values: list[str]) -> str:
    return "".join(f"<li>{_escape(value)}</li>" for value in values if value)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = " ".join(str(value or "").split())
        key = clean.lower()
        if not clean or key in seen:
            continue
        seen.add(key)
        result.append(clean)
    return result


def _deadline_assessment(model: dict[str, Any]) -> tuple[str, str, str]:
    """Return customer recommendation, deadline status and next action.

    The only time comparison is between timestamps already persisted in the
    accepted canonical model. No wall clock or external source is consulted.
    """

    projection = build_customer_report_projection(model)
    deadline_display = str(
        projection.get("application_deadline_display")
        or "Данных недостаточно — требуется проверка"
    )
    deadline = _report_model._parse_timestamp(model.get("application_deadline"))
    analysis_as_of = _report_model._parse_timestamp(
        model.get("analysis_as_of_iso") or model.get("analysis_as_of")
    )

    relation: str | None = None
    if deadline is not None and analysis_as_of is not None:
        try:
            relation = "expired" if analysis_as_of > deadline else "open_at_analysis"
        except TypeError:
            relation = None

    if relation == "expired":
        return (
            "НЕ УЧАСТВОВАТЬ — срок подачи заявок истёк",
            f"Срок подачи по документам: {deadline_display}. "
            "К моменту формирования анализа срок уже истёк.",
            "Участие в этой процедуре не планировать. Для ретроспективной "
            "оценки можно использовать приведённые ниже факты и ограничения.",
        )
    if relation == "open_at_analysis":
        return (
            "HOLD — сначала завершить коммерческую и документарную проверку",
            f"Срок подачи по документам: {deadline_display}. На момент "
            "формирования анализа срок ещё не истёк.",
            "До решения об участии закрыть ограничения автоматического "
            "извлечения и рассчитать экономику участия.",
        )
    return (
        "HOLD — сначала вручную подтвердить актуальность срока подачи",
        f"Срок подачи по документам: {deadline_display}. Текущий статус срока "
        "не удалось подтвердить по сохранённым временным данным.",
        "Сначала вручную подтвердить актуальность срока подачи, затем закрыть "
        "ограничения автоматического извлечения и рассчитать экономику участия.",
    )


def _row_identity(row: dict[str, Any]) -> tuple[str, str]:
    return (
        " ".join(str(row.get("title") or "").lower().split()),
        " ".join(str(row.get("detail") or "").lower().split()),
    )


def _application_rows_are_duplicates(detail: dict[str, Any]) -> bool:
    application = [
        row for row in detail.get("application_requirements", []) if isinstance(row, dict)
    ]
    technical = [
        row for row in detail.get("technical_requirements", []) if isinstance(row, dict)
    ]
    if not application:
        return False
    technical_keys = {_row_identity(row) for row in technical}
    return all(_row_identity(row) in technical_keys for row in application)


def _customer_limitations(
    model: dict[str, Any], rendered_html: str
) -> tuple[list[str], bool]:
    projection = build_customer_report_projection(model)
    detail = build_customer_detail_projection(model)
    limitations: list[str] = []

    line_items = [
        row for row in projection.get("line_items", []) if isinstance(row, dict)
    ]
    if line_items and all(not row.get("characteristics") for row in line_items):
        limitations.append(
            "Детальные характеристики товара в текущем автоматическом "
            "извлечении не представлены; перед коммерческим решением нужно "
            "сверить ТЗ вручную."
        )

    payment_items: list[str] = []
    has_security_group = False
    for group in detail.get("contract_term_groups", []):
        if not isinstance(group, dict):
            continue
        title = str(group.get("title") or "")
        items = [str(item) for item in group.get("items", []) if item]
        if title == "Оплата":
            payment_items.extend(items)
        if title == "Обеспечение" and items:
            has_security_group = True

    if not payment_items:
        limitations.append(
            "Конкретный срок и порядок оплаты в текущем отчёте не извлечены; "
            "их нужно проверить по проекту контракта."
        )
    elif all(_GENERIC_PAYMENT_MARKER in item.lower() for item in payment_items):
        limitations.append(
            "Наличие условий оплаты подтверждено, но конкретный срок и порядок "
            "оплаты в текущем отчёте не извлечены."
        )

    if not has_security_group:
        limitations.append(
            "Размер и условия обеспечения исполнения контракта в текущем "
            "отчёте не извлечены."
        )

    if "Коммерческие предложения не загружены" in rendered_html:
        limitations.append(
            "Коммерческие предложения не загружены, поэтому маржинальность и "
            "экономика участия не рассчитаны."
        )

    duplicate_application_rows = _application_rows_are_duplicates(detail)
    if duplicate_application_rows:
        limitations.append(
            "Отдельные требования к составу заявки и участнику автоматически "
            "не выделены: текущая классификация пересекается с требованиями к товару."
        )

    return _dedupe(limitations), duplicate_application_rows


def _replace_decision_section(model: dict[str, Any], rendered_html: str) -> str:
    matches = list(_DECISION_SECTION_RE.finditer(rendered_html))
    if len(matches) != 1:
        raise AcceptanceBlocked("customer_report_decision_section_invalid")

    projection = build_customer_report_projection(model)
    decision = projection.get("customer_decision")
    decision = decision if isinstance(decision, dict) else {}
    recommendation, deadline_status, next_action = _deadline_assessment(model)

    reasons = [str(item) for item in decision.get("reasons", []) if item]
    if "Коммерческие предложения не загружены" in rendered_html:
        reasons.append(
            "Экономика участия не рассчитана: коммерческие предложения не загружены."
        )
    reasons = _dedupe([deadline_status, *reasons])

    section = (
        '<section class="decision">'
        f"<h2>Предварительная рекомендация: {_escape(recommendation)}</h2>"
        f"<p><strong>Статус срока подачи:</strong> {_escape(deadline_status)}</p>"
        f"<h3>Основания</h3><ul>{_bullets(reasons)}</ul>"
        f"<p><strong>Следующее действие:</strong> {_escape(next_action)}</p>"
        "</section>"
    )
    return _DECISION_SECTION_RE.sub(
        lambda _match: section, rendered_html, count=1
    )


def _replace_duplicate_application_section(
    rendered_html: str, *, duplicate_application_rows: bool
) -> str:
    if not duplicate_application_rows:
        return rendered_html
    replacement = (
        "<section><h2>Требования к заявке и участнику</h2>"
        "<p>Отдельные требования к составу заявки и участнику в текущем "
        "автоматическом извлечении не выделены. Перед подачей заявки требуется "
        "ручная проверка соответствующего приложения закупочной документации.</p>"
        "</section>"
    )
    return _APPLICATION_SECTION_RE.sub(replacement, rendered_html, count=1)


def _replace_questions_with_checklist(rendered_html: str) -> str:
    checklist = [
        "Сверить точные характеристики товара и применимые ГОСТ/ТУ по ТЗ.",
        "Проверить конкретный срок и порядок оплаты по проекту контракта.",
        "Проверить размер, форму и условия обеспечения исполнения контракта.",
        "Сверить количество, единицу измерения и расчёт НМЦК с ценовым приложением.",
        "До участия рассчитать собственную себестоимость, логистику и минимальную цену предложения.",
    ]
    replacement = (
        "<section><h2>Контроль перед коммерческим решением</h2>"
        f"<ul>{_bullets(checklist)}</ul>"
        "<p>Этот список — общий контроль участника закупки, а не утверждение, "
        "что перечисленные параметры отсутствуют в исходных документах.</p>"
        "</section>"
    )
    if _QUESTIONS_SECTION_RE.search(rendered_html):
        return _QUESTIONS_SECTION_RE.sub(replacement, rendered_html, count=1)
    if _COMMERCIAL_SECTION_MARKER in rendered_html:
        return rendered_html.replace(
            _COMMERCIAL_SECTION_MARKER,
            replacement + _COMMERCIAL_SECTION_MARKER,
            1,
        )
    return rendered_html + replacement


def _insert_limitations(rendered_html: str, limitations: list[str]) -> str:
    if not limitations:
        return rendered_html
    section = (
        "<section><h2>Ограничения текущего автоматического извлечения</h2>"
        f"<ul>{_bullets(limitations)}</ul>"
        "</section>"
    )
    if _COMMERCIAL_SECTION_MARKER in rendered_html:
        return rendered_html.replace(
            _COMMERCIAL_SECTION_MARKER,
            section + _COMMERCIAL_SECTION_MARKER,
            1,
        )
    return rendered_html + section


def _correct_empty_characteristics_claim(
    model: dict[str, Any], rendered_html: str
) -> str:
    projection = build_customer_report_projection(model)
    line_items = [
        row for row in projection.get("line_items", []) if isinstance(row, dict)
    ]
    if line_items and all(not row.get("characteristics") for row in line_items):
        return rendered_html.replace(
            "<p>Подробные требования приведены ниже в разделе «Технические требования».</p>",
            "<p>В текущем автоматическом извлечении детальные характеристики "
            "позиции не подтверждены; перед коммерческим решением требуется "
            "ручная сверка ТЗ.</p>",
            1,
        )
    return rendered_html


def _sanitize_raw_source_cells(rendered_html: str) -> str:
    cell_re = re.compile(r"<td>(.*?)</td>", re.DOTALL)

    def replace_cell(match: re.Match[str]) -> str:
        content = match.group(1)
        if _RAW_SOURCE_FILE_RE.search(html.unescape(content)):
            return "<td>Документы закупки</td>"
        return match.group(0)

    return cell_re.sub(replace_cell, rendered_html)


def _validate_customer_rework(reworked_html: str) -> None:
    lowered = reworked_html.lower()
    if any(value in lowered for value in _FORBIDDEN_READINESS_PHRASES):
        raise AcceptanceBlocked("arv001_independent_review_readiness_forbidden")
    if any(value in reworked_html for value in _INTERNAL_CUSTOMER_FORBIDDEN):
        raise AcceptanceBlocked("arv001_internal_governance_exposed_to_customer")
    if _RAW_SOURCE_FILE_RE.search(html.unescape(reworked_html)):
        raise AcceptanceBlocked("arv001_raw_source_identifier_exposed")
    if '<section class="decision"><h2>Решение:' in reworked_html:
        raise AcceptanceBlocked("arv001_ambiguous_decision_label_present")
    if "Предварительная рекомендация:" not in reworked_html:
        raise AcceptanceBlocked("arv001_customer_recommendation_missing")
    if "Контроль перед коммерческим решением" not in reworked_html:
        raise AcceptanceBlocked("arv001_customer_checklist_missing")


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
    limitations, duplicate_application_rows = _customer_limitations(model, rendered)
    reworked = _replace_decision_section(model, rendered)
    reworked = _correct_empty_characteristics_claim(model, reworked)
    reworked = _replace_duplicate_application_section(
        reworked,
        duplicate_application_rows=duplicate_application_rows,
    )
    reworked = _insert_limitations(reworked, limitations)
    reworked = _replace_questions_with_checklist(reworked)
    reworked = _sanitize_raw_source_cells(reworked)

    validate_customer_report(reworked, expected_registry_number)
    _validate_customer_rework(reworked)
    if _canonical_bytes(model) != before:
        raise AcceptanceBlocked("canonical_report_mutated_during_rework")
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
                "customer_html_internal_governance_exposed": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
