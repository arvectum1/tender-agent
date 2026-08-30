#!/usr/bin/env python3
"""Compress an ARV-001 human-facing candidate without changing evidence.

This is a deterministic presentation-only pass. It keeps the complete source-bound
fact/evidence corpus in a collapsed audit appendix so existing fail-closed material
validation still proves that nothing was lost, while the default human view shows
only ranked, deduplicated, decision-relevant information.

No provider, EIS, RAG, quality-acceptance, acknowledgement, DB, Git, canonical, or
frozen-source mutation is performed.
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
from typing import Any, Iterable

from scripts.arv001.complete_corpus_contract import AcceptanceBlocked, validate_customer_report
from scripts.arv001.finalize_human_decision_contract import validate_human_decision_contract
from scripts.arv001.validate_decision_useful_candidate import validate_rendered_material_terms

_DECISION_RE = re.compile(r'<section class="decision"[^>]*>.*?</section>', re.DOTALL)
_WORD_HYPERLINK_RE = re.compile(
    r'HYPERLINK\s+"[^"]+"(?:\s+\\l\s+"[^"]+")?\s*', re.IGNORECASE
)


def _section_re(title: str) -> re.Pattern[str]:
    return re.compile(
        rf"<section><h2>{re.escape(title)}</h2>.*?</section>", re.DOTALL
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split()).strip()


def _escape(value: Any) -> str:
    return html.escape(_normalize(value))


def _read_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcceptanceBlocked(code) from exc
    if not isinstance(value, dict):
        raise AcceptanceBlocked(code)
    return value


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in (value or []) if isinstance(row, dict) and _normalize(row.get("text"))]


def _contract_rows(analysis: dict[str, Any], key: str) -> list[dict[str, Any]]:
    contract = analysis.get("contract")
    contract = contract if isinstance(contract, dict) else {}
    return _rows(contract.get(key))


def _row_ids(row: dict[str, Any]) -> list[str]:
    values = [str(value) for value in row.get("evidence_ids") or [] if value]
    if not values and row.get("evidence_id"):
        values = [str(row["evidence_id"])]
    return values


def _ids_attr(ids: Iterable[str]) -> str:
    return html.escape(" ".join(str(value) for value in ids if value))


def _pick(rows: list[dict[str, Any]], *needles: str) -> dict[str, Any] | None:
    lowered = [needle.casefold() for needle in needles]
    for row in rows:
        text = _normalize(row.get("text"))
        folded = text.casefold()
        if all(needle in folded for needle in lowered):
            return row
    return None


def _clean_word_fields(text: str) -> str:
    clean = _WORD_HYPERLINK_RE.sub("", _normalize(text))
    clean = re.sub(r"\s+([,.;:])", r"\1", clean)
    return clean.strip()


def _evidenced_li(text: str, ids: Iterable[str]) -> str:
    return (
        f'<li data-evidence-ids="{_ids_attr(ids)}">{_escape(text)}</li>'
    )


def _audit_appendix(contract: dict[str, Any]) -> str:
    facts = [item for item in contract.get("facts") or [] if isinstance(item, dict)]
    uncertainty = [
        item for item in contract.get("uncertainty") or [] if isinstance(item, dict)
    ]
    caveats = [item for item in contract.get("caveats") or [] if isinstance(item, dict)]

    fact_rows = "".join(
        '<li data-claim-kind="fact" '
        f'data-evidence-ids="{_ids_attr(item.get("evidence_ids") or [])}">'
        f'<strong>{_escape(item.get("label"))}:</strong> {_escape(item.get("text"))} '
        f'<span>Evidence ID: {_escape(", ".join(item.get("evidence_ids") or []))}</span></li>'
        for item in facts
    )
    uncertainty_rows = "".join(
        '<li data-claim-kind="uncertainty" '
        f'data-evidence-ids="{_ids_attr(item.get("evidence_ids") or [])}">'
        f'{_escape(item.get("text"))} '
        f'<span>Evidence ID: {_escape(", ".join(item.get("evidence_ids") or []))}</span></li>'
        for item in uncertainty
    )
    caveat_rows = "".join(
        '<li data-claim-kind="caveat" '
        f'data-evidence-ids="{_ids_attr(item.get("evidence_ids") or [])}">'
        f'{_escape(item.get("text"))} '
        f'<span>Evidence ID: {_escape(", ".join(item.get("evidence_ids") or []))}</span></li>'
        for item in caveats
    )
    return (
        '<details class="audit-evidence"><summary>Доказательная база и Evidence ID — для проверки</summary>'
        '<p>Ниже сохранены исходные извлечённые фрагменты без аналитического сокращения. '
        'Они нужны для аудита и автоматической проверки, но не являются основной частью отчёта.</p>'
        f'<h4>Факты</h4><ul>{fact_rows}</ul>'
        f'<h4>Неопределённости</h4><ul>{uncertainty_rows}</ul>'
        f'<h4>Оговорки</h4><ul>{caveat_rows}</ul>'
        '</details>'
    )


def _compact_decision(contract: dict[str, Any], analysis: dict[str, Any]) -> str:
    decision = contract.get("decision") if isinstance(contract.get("decision"), dict) else {}
    next_action = contract.get("next_action") if isinstance(contract.get("next_action"), dict) else {}
    uncertainty = [
        item for item in contract.get("uncertainty") or [] if isinstance(item, dict)
    ]
    caveats = [item for item in contract.get("caveats") or [] if isinstance(item, dict)]

    technical = analysis.get("technical")
    technical = technical if isinstance(technical, dict) else {}
    technical_rows = _rows(technical.get("specific_clauses"))
    payment = _contract_rows(analysis, "payment")
    security = _contract_rows(analysis, "security")

    key_points: list[str] = []
    for row in technical_rows[:2]:
        key_points.append(_evidenced_li(_clean_word_fields(_normalize(row.get("text"))), _row_ids(row)))
    no_advance = _pick(payment, "аванс не предусмотрен")
    if no_advance:
        key_points.append(_evidenced_li("Аванс не предусмотрен.", _row_ids(no_advance)))
    pay_7 = _pick(payment, "7 (семи) рабочих дней") or _pick(payment, "7 рабочих дней")
    if pay_7:
        key_points.append(
            _evidenced_li(
                "Оплата — не позднее 7 рабочих дней после подписания заказчиком документа о приёмке в ЕИС.",
                _row_ids(pay_7),
            )
        )
    sec_amount = _pick(security, "составляет", "_______", "руб")
    if sec_amount:
        key_points.append(
            _evidenced_li(
                "Размер обеспечения исполнения в проекте контракта не заполнен — финансовую нагрузку пока нельзя посчитать.",
                _row_ids(sec_amount),
            )
        )

    uncertainty_html = "".join(
        _evidenced_li(_clean_word_fields(_normalize(item.get("text"))), item.get("evidence_ids") or [])
        for item in uncertainty
    ) or "<li>Существенных неопределённостей в пределах зафиксированного корпуса не выявлено.</li>"
    caveat_html = "".join(
        _evidenced_li(_clean_word_fields(_normalize(item.get("text"))), item.get("evidence_ids") or [])
        for item in caveats
    )

    return (
        '<section class="decision" data-arv001-human-decision-contract="v1" data-presentation="compressed-v1">'
        '<h2>Решение</h2>'
        f'<p data-claim-kind="interpretation" data-evidence-ids="{_ids_attr(decision.get("evidence_ids") or [])}">'
        f'<strong>Предварительная рекомендация:</strong> {_escape(decision.get("text"))}</p>'
        '<h3>Почему</h3>'
        f'<ul>{"".join(key_points)}</ul>'
        '<h3>Неопределённость</h3>'
        f'<ul>{uncertainty_html}</ul>'
        '<h3>Оговорки и ограничения</h3>'
        f'<ul>{caveat_html}</ul>'
        '<h3>Следующее действие</h3>'
        f'<p data-claim-kind="recommendation" data-evidence-ids="{_ids_attr(next_action.get("evidence_ids") or [])}">'
        f'{_escape(next_action.get("text"))}</p>'
        + _audit_appendix(contract)
        + '</section>'
    )


def _technical_section(analysis: dict[str, Any]) -> str:
    technical = analysis.get("technical")
    technical = technical if isinstance(technical, dict) else {}
    rows = _rows(technical.get("specific_clauses"))
    standards = [_normalize(item) for item in technical.get("standards") or [] if _normalize(item)]

    body = "".join(
        '<tr>'
        f'<td>{_escape(_clean_word_fields(_normalize(row.get("text"))))}</td>'
        f'<td>{_escape(row.get("source") or "Техническое задание")}</td>'
        '</tr>'
        for row in rows
    )
    if standards:
        standard_text = "; ".join(standards)
        body += f'<tr><td>Применимые стандарты: {_escape(standard_text)}</td><td>Техническое задание</td></tr>'
    return (
        '<section><h2>Технические требования</h2>'
        '<p><strong>Для решения об участии:</strong> ниже только конкретные характеристики товара, которые удалось подтвердить по ТЗ.</p>'
        '<div class="scroll"><table><thead><tr><th>Подтверждённое требование</th><th>Источник</th></tr></thead>'
        f'<tbody>{body}</tbody></table></div>'
        '</section>'
    )


def _application_section(analysis: dict[str, Any]) -> str:
    rows = _rows(analysis.get("application_requirements"))
    selected: list[tuple[str, str, list[str]]] = []

    def add(label: str, row: dict[str, Any] | None, override: str | None = None) -> None:
        if not row:
            return
        selected.append((label, override or _clean_word_fields(_normalize(row.get("text"))), _row_ids(row)))

    add("Регистрационные сведения", _pick(rows, "выписка из единого государственного реестра"))
    add("Требования к участнику", _pick(rows, "дополнительным требованиям", "не установлены"), "Дополнительные требования по ч. 2 и 2.1 ст. 31 Закона № 44-ФЗ: не установлены.")
    add("Декларация участника", _pick(rows, "пунктами 3–5, 7–11", "статьи 31"))
    add("Документы на товар", _pick(rows, "документы, подтверждающие соответствие товара"))
    add("Крупная сделка — если применимо", _pick(rows, "крупной сделки"))

    origin = _pick(rows, "подтверждающие страну происхождения товара")
    origin_effect = _pick(rows, "приравнивается к заявке", "иностранного государства")
    if origin or origin_effect:
        ids = [*_row_ids(origin or {}), *_row_ids(origin_effect or {})]
        selected.append(
            (
                "Страна происхождения / нацрежим",
                "Нужно проверить и при необходимости представить сведения/документы о стране происхождения. При их отсутствии заявка рассматривается как предложение иностранного товара в предусмотренных документацией случаях.",
                ids,
            )
        )

    conditional_rows = [
        row
        for row in rows
        if any(
            needle in _normalize(row.get("text")).casefold()
            for needle in (
                "уголовно-исполнительной системы",
                "организации инвалидов",
                "социально ориентированным некоммерческим",
            )
        )
    ]
    if conditional_rows:
        ids = [value for row in conditional_rows for value in _row_ids(row)]
        selected.append(
            (
                "Специальные статусы — только если применимо",
                "Декларации о специальных статусах/преимуществах (УИС, организация инвалидов, СОНКО) требуются только при применимости соответствующего статуса или преимущества.",
                ids,
            )
        )

    body = "".join(
        '<tr>'
        f'<td>{_escape(label)}</td><td data-evidence-ids="{_ids_attr(ids)}">{_escape(text)}</td>'
        '</tr>'
        for label, text, ids in selected
    )
    return (
        '<section><h2>Требования к заявке и участнику</h2>'
        '<p>Показаны только требования, которые влияют на комплектность заявки или риск отклонения; заголовки и служебные Word-поля скрыты.</p>'
        '<div class="scroll"><table><thead><tr><th>Что проверить/подготовить</th><th>Содержание</th></tr></thead>'
        f'<tbody>{body}</tbody></table></div>'
        '</section>'
    )


def _contract_section(analysis: dict[str, Any]) -> str:
    payment = _contract_rows(analysis, "payment")
    security = _contract_rows(analysis, "security")
    acceptance = _contract_rows(analysis, "acceptance")
    liability = _contract_rows(analysis, "liability")
    cap = _contract_rows(analysis, "liability_cap")
    termination = _contract_rows(analysis, "termination")

    groups: list[tuple[str, list[str]]] = []

    pay_items: list[str] = []
    row = _pick(payment, "аванс не предусмотрен")
    if row:
        pay_items.append(_evidenced_li("Аванс: не предусмотрен.", _row_ids(row)))
    row = _pick(payment, "7 (семи) рабочих дней") or _pick(payment, "7 рабочих дней")
    if row:
        pay_items.append(_evidenced_li("Оплата: не позднее 7 рабочих дней после подписания заказчиком документа о приёмке в ЕИС.", _row_ids(row)))
    row = _pick(payment, "18 сентября 2026")
    if row:
        pay_items.append(_evidenced_li("Срок действия контракта с учётом приёмки и оплаты — по 18 сентября 2026 года; взаиморасчёты — до полного исполнения.", _row_ids(row)))
    groups.append(("Оплата", pay_items))

    security_items: list[str] = []
    amount = _pick(security, "составляет", "_______", "руб")
    if amount:
        security_items.append(_evidenced_li("Размер обеспечения исполнения: в проекте контракта не заполнен (оставлено шаблонное поле).", _row_ids(amount)))
    guarantee_a = _pick(security, "независимой гарантии", "ст")
    guarantee_b = _pick(security, "45 фз", "внесением денежных средств")
    if guarantee_a or guarantee_b:
        ids = [*_row_ids(guarantee_a or {}), *_row_ids(guarantee_b or {})]
        security_items.append(_evidenced_li("Форма обеспечения: независимая гарантия по требованиям ст. 45 Закона № 44-ФЗ либо внесение денежных средств.", ids))
    guarantee_term = _pick(security, "не менее чем на один месяц")
    if guarantee_term:
        security_items.append(_evidenced_li("Срок независимой гарантии должен превышать срок обеспечиваемых обязательств минимум на 1 месяц.", _row_ids(guarantee_term)))
    cash_return = _pick(security, "возвращаются", "15 (пятнадцати) дней")
    if cash_return:
        security_items.append(_evidenced_li("Денежное обеспечение при наличии оснований возвращается в течение 15 дней после исполнения обязательств.", _row_ids(cash_return)))
    antidumping = _pick(security, "двадцать пять и более процентов")
    if antidumping:
        security_items.append(_evidenced_li("При снижении цены на 25% и более применяются требования ст. 37 Закона № 44-ФЗ к обеспечению.", _row_ids(antidumping)))
    groups.append(("Обеспечение исполнения", security_items))

    acceptance_items: list[str] = []
    row = _pick(acceptance, "4 (четырех) рабочих дней")
    if row:
        acceptance_items.append(_evidenced_li("Поставщик размещает документ о приёмке в ЕИС в течение 4 рабочих дней после фактической передачи товара.", _row_ids(row)))
    row = _pick(acceptance, "20 (двадцати) рабочих дней")
    if row:
        acceptance_items.append(_evidenced_li("У заказчика — до 20 рабочих дней после поступления документа о приёмке на приёмку либо мотивированный отказ.", _row_ids(row)))
    row = _pick(acceptance, "мотивированный отказ", "перечнем выявленных недостатков")
    if row:
        acceptance_items.append(_evidenced_li("При несоответствиях заказчик вправе оформить мотивированный отказ с перечнем недостатков и сроком их устранения.", _row_ids(row)))
    groups.append(("Приёмка", acceptance_items))

    liability_items: list[str] = []
    row = _pick(liability, "одной трехсотой", "ключевой ставки")
    if row:
        liability_items.append(_evidenced_li("Пеня за просрочку поставщика: 1/300 ключевой ставки за каждый день по базе, определённой контрактом.", _row_ids(row)))
    row = _pick(liability, "1 % от цены контракта", "не более 5 тыс")
    if row:
        liability_items.append(_evidenced_li("Один из предусмотренных штрафов: 1% от цены контракта (этапа), но не более 5 тыс. руб. — применимость зависит от указанного в контракте случая.", _row_ids(row)))
    if cap:
        liability_items.append(_evidenced_li("Совокупная сумма начисленных поставщику штрафов не может превышать цену контракта.", _row_ids(cap[0])))
    groups.append(("Ответственность", liability_items))

    termination_items: list[str] = []
    row = _pick(termination, "расторжение контракта допускается")
    if row:
        termination_items.append(_evidenced_li("Расторжение допускается по соглашению сторон, по решению суда либо при одностороннем отказе в предусмотренных законом случаях.", _row_ids(row)))
    groups.append(("Расторжение", termination_items))

    rendered_groups = "".join(
        f'<h3>{_escape(title)}</h3><ul>{"".join(items)}</ul>'
        for title, items in groups
        if items
    )
    return (
        '<section><h2>Условия контракта</h2>'
        '<p>Ниже — только условия, которые непосредственно влияют на деньги, сроки исполнения и риск поставщика.</p>'
        + rendered_groups
        + '</section>'
    )


def _remaining_checks(contract: dict[str, Any], original_html: str) -> str:
    uncertainty = [
        item for item in contract.get("uncertainty") or [] if isinstance(item, dict)
    ]
    by_code = {str(item.get("code")): item for item in uncertainty}
    checks: list[str] = []
    if "deadline_not_confirmed" in by_code:
        item = by_code["deadline_not_confirmed"]
        checks.append(_evidenced_li("Проверить текущий статус процедуры и срок подачи в актуальном источнике.", item.get("evidence_ids") or []))
    if "performance_security_amount_unresolved" in by_code:
        item = by_code["performance_security_amount_unresolved"]
        checks.append(_evidenced_li("Уточнить конкретный размер обеспечения исполнения и посчитать стоимость гарантии либо отвлечения денежных средств.", item.get("evidence_ids") or []))
    if "commercial_economics_not_calculated" in by_code:
        item = by_code["commercial_economics_not_calculated"]
        checks.append(_evidenced_li("Рассчитать себестоимость товара, логистику, обеспечение и минимально допустимую цену предложения.", item.get("evidence_ids") or []))
    if "ЧУКОТСК" in original_html.upper() and "Архангельск" in original_html:
        checks.append("<li>Отдельно перепроверить место поставки и логистический маршрут: в отчёте заказчик — Чукотское УГМС, а адрес поставки указан в Архангельске.</li>")
    return (
        '<section><h2>Что осталось проверить</h2>'
        '<p>Только незакрытые вопросы; уже извлечённые характеристики и условия оплаты повторно проверять по шаблону не предлагается.</p>'
        f'<ul>{"".join(checks)}</ul>'
        '</section>'
    )


def _replace_section(rendered: str, title: str, replacement: str) -> str:
    pattern = _section_re(title)
    if pattern.search(rendered):
        return pattern.sub(lambda _match: replacement, rendered, count=1)
    return rendered


def _remove_section(rendered: str, title: str) -> str:
    return _section_re(title).sub("", rendered, count=1)


def _improve_composition_section(rendered: str, analysis: dict[str, Any]) -> str:
    pattern = _section_re("Состав и объём закупки")
    match = pattern.search(rendered)
    if not match:
        return rendered
    section = match.group(0)
    technical = analysis.get("technical")
    technical = technical if isinstance(technical, dict) else {}
    texts = [_normalize(row.get("text")) for row in _rows(technical.get("specific_clauses"))]
    characteristics: list[str] = []
    for text in texts:
        fuel = re.search(r"Сорт/класс топлива\s+Не ниже\s+([^\s]+)", text, re.IGNORECASE)
        eco = re.search(r"Экологический класс\s+Не ниже\s+([КK]\s*\d+)", text, re.IGNORECASE)
        if fuel:
            characteristics.append(f"сорт/класс топлива ≥ {fuel.group(1)}")
        if eco:
            characteristics.append(f"экологический класс ≥ {eco.group(1).replace(' ', '')}")
    if characteristics:
        section = section.replace("<td>—</td>", f"<td>{_escape('; '.join(characteristics))}</td>", 1)
        section = section.replace(
            "<p>Подробные требования приведены ниже в разделе «Технические требования».</p>",
            "<p>Ключевые характеристики подтверждены по ТЗ; полный исходный фрагмент доступен в доказательной базе.</p>",
            1,
        )
    return rendered[: match.start()] + section + rendered[match.end() :]


def compress_html(original_html: str, analysis: dict[str, Any], contract: dict[str, Any]) -> str:
    rendered = _DECISION_RE.sub(
        lambda _match: _compact_decision(contract, analysis), original_html, count=1
    )
    if rendered == original_html:
        raise AcceptanceBlocked("compressed_report_decision_section_missing")

    rendered = _improve_composition_section(rendered, analysis)
    rendered = _replace_section(rendered, "Технические требования", _technical_section(analysis))
    rendered = _replace_section(rendered, "Требования к заявке и участнику", _application_section(analysis))
    rendered = _replace_section(rendered, "Условия контракта", _contract_section(analysis))
    rendered = _remove_section(rendered, "Ограничения текущего автоматического извлечения")
    rendered = _replace_section(rendered, "Контроль перед коммерческим решением", _remaining_checks(contract, original_html))
    rendered = _remove_section(rendered, "Источники")
    return rendered


def validate_compressed_presentation(rendered: str) -> None:
    decision_match = _DECISION_RE.search(rendered)
    if not decision_match:
        raise AcceptanceBlocked("compressed_report_decision_missing")
    decision_html = decision_match.group(0)
    audit_marker = '<details class="audit-evidence">'
    if audit_marker not in decision_html:
        raise AcceptanceBlocked("compressed_report_audit_appendix_missing")
    visible_decision = decision_html.split(audit_marker, 1)[0]
    if "Evidence ID:" in visible_decision:
        raise AcceptanceBlocked("compressed_report_evidence_ids_exposed_by_default")
    if "HYPERLINK" in visible_decision or "\\l &quot;dst" in visible_decision:
        raise AcceptanceBlocked("compressed_report_word_field_exposed_by_default")
    for title in (
        "Технические требования",
        "Требования к заявке и участнику",
        "Условия контракта",
        "Что осталось проверить",
    ):
        if f"<h2>{title}</h2>" not in rendered:
            raise AcceptanceBlocked("compressed_report_required_section_missing")
    if "Проверить конкретный срок и порядок оплаты" in rendered:
        raise AcceptanceBlocked("compressed_report_stale_generic_checklist_present")
    if "РАСТОРЖЕНИЯ КОНТРАКТА" in rendered.split(audit_marker, 1)[0]:
        raise AcceptanceBlocked("compressed_report_heading_promoted_to_fact")


def compress_candidate(*, output_root: Path) -> dict[str, Any]:
    root = output_root.expanduser().resolve(strict=True)
    html_path = root / "upload-ready-report-decision-useful.html"
    analysis_path = root / "decision-useful-analysis.json"
    contract_path = root / "human-decision-contract.json"
    manifest_path = root / "candidate-manifest.json"

    try:
        original_html_bytes = html_path.read_bytes()
    except OSError as exc:
        raise AcceptanceBlocked("compressed_report_html_unreadable") from exc
    try:
        original_html = original_html_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AcceptanceBlocked("compressed_report_html_invalid_utf8") from exc

    analysis = _read_json(analysis_path, "compressed_report_analysis_invalid")
    contract = _read_json(contract_path, "compressed_report_contract_invalid")
    manifest = _read_json(manifest_path, "compressed_report_manifest_invalid")

    if manifest.get("report_sha256") != _sha256(original_html_bytes):
        raise AcceptanceBlocked("compressed_report_input_hash_mismatch")
    if manifest.get("analysis_sha256") != _sha256(analysis_path.read_bytes()):
        raise AcceptanceBlocked("compressed_report_analysis_hash_mismatch")
    if manifest.get("human_decision_contract_sha256") != _sha256(contract_path.read_bytes()):
        raise AcceptanceBlocked("compressed_report_contract_hash_mismatch")
    gate = manifest.get("decision_usefulness_gate")
    if not isinstance(gate, dict) or gate.get("status") != "PASS":
        raise AcceptanceBlocked("compressed_report_requires_decision_usefulness_pass")
    if manifest.get("human_decision_contract_status") != "PASS":
        raise AcceptanceBlocked("compressed_report_requires_human_contract_pass")

    rendered = compress_html(original_html, analysis, contract)
    validate_compressed_presentation(rendered)

    registry_number = _normalize(manifest.get("registry_number"))
    if not registry_number:
        raise AcceptanceBlocked("compressed_report_registry_number_missing")
    validate_customer_report(rendered, registry_number)
    material_validation = validate_rendered_material_terms(rendered, analysis)
    contract_validation = validate_human_decision_contract(rendered, contract)

    html_bytes = rendered.encode("utf-8")
    final_manifest = dict(manifest)
    final_manifest.update(
        {
            "schema_version": "arv001-decision-useful-candidate-v3",
            "status": "human_decision_relevance_compressed_candidate_for_product_owner_review",
            "report_sha256": _sha256(html_bytes),
            "human_decision_contract_validation": contract_validation,
            "presentation_compression": {
                "status": "PASS",
                "version": "compressed-v1",
                "raw_evidence_default_collapsed": True,
                "evidence_corpus_mutated": False,
                "analysis_mutated": False,
                "contract_mutated": False,
                "rendered_material_validation": material_validation,
            },
            "product_owner": "REJECTED",
            "independent_review": "NOT_AUTHORIZED",
            "freeze": "NOT_ALLOWED",
            "required_action": "RELEVANCE_COMPRESSED_REPORT_REVIEW_REQUIRED",
        }
    )
    manifest_bytes = (
        json.dumps(final_manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")

    _atomic_write(html_path, html_bytes)
    _atomic_write(manifest_path, manifest_bytes)

    return {
        "status": "relevance_compressed_candidate_for_product_owner_review",
        "marker": "ARV001_HUMAN_REPORT_COMPRESSED_READY",
        "report_sha256": final_manifest["report_sha256"],
        "manifest_sha256": _sha256(manifest_bytes),
        "analysis_sha256": final_manifest.get("analysis_sha256"),
        "human_decision_contract_sha256": final_manifest.get("human_decision_contract_sha256"),
        "decision_usefulness_gate": "PASS",
        "human_decision_contract": "PASS",
        "rendered_material_validation": material_validation,
        "presentation_compression": "PASS",
        "product_owner": "REJECTED",
        "independent_review": "NOT_AUTHORIZED",
        "freeze": "NOT_ALLOWED",
        "provider_calls_performed": False,
        "eis_requests_performed": False,
        "rag_rerun": False,
        "quality_acceptance_rerun": False,
        "git_mutations": 0,
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compress an ARV-001 human-facing candidate without changing evidence.")
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    result = compress_candidate(output_root=args.output_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
