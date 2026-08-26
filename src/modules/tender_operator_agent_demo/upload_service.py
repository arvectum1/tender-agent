"""Compatibility facade for tender report persistence and rendering.

The historical upload implementation remains intact in ``upload_service_legacy``.
This facade exposes the same API while routing R10.1 reports through a separate,
sanitized customer projection.
"""

from __future__ import annotations

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from typing import Any

from src.modules.tender_operator_agent_demo import upload_service_legacy as _legacy

for _name, _value in vars(_legacy).items():
    if _name not in {"__name__", "__package__", "__loader__", "__spec__"}:
        globals().setdefault(_name, _value)

_ORIGINAL_BUILD_PRELIMINARY_PROCUREMENT_ANALYSIS = (
    _legacy._build_preliminary_procurement_analysis
)
_ORIGINAL_EXTRACT_SUPPLY_ITEMS_FROM_NOTIFICATION_XML = (
    _legacy._extract_supply_items_from_notification_xml
)
_ORIGINAL_ENRICH_PROCUREMENT_METADATA_FROM_DOCUMENTS = (
    _legacy._enrich_procurement_metadata_from_documents
)


def _liability_contract_highlight(contract_text: str) -> str | None:
    """Return a conservative grounded liability summary from the contract text."""

    lowered = contract_text.lower()
    has_liability = bool(
        re.search(r"ответственност[ьи]\s+(?:сторон|поставщика|заказчика)", lowered)
        or "ответственность сторон" in lowered
    )
    has_sanctions = bool(
        re.search(r"\b(?:штраф|штрафы|штрафа|штрафов|пеня|пени|неустойк)\w*", lowered)
    )
    if has_liability and has_sanctions:
        return (
            "Проект контракта содержит условия ответственности сторон и "
            "штрафные санкции за нарушение обязательств."
        )
    if has_sanctions:
        return (
            "Проект контракта содержит условия о штрафах, пенях или неустойке "
            "за нарушение обязательств."
        )
    if has_liability:
        return "Проект контракта содержит раздел об ответственности сторон."
    return None


def _payment_contract_highlight(contract_text: str) -> str | None:
    """Flag a source-backed payment section without inventing missing terms."""

    normalized = " ".join(contract_text.lower().split())
    if not normalized:
        return None
    grounded_markers = (
        r"\b(?:условия|порядок)\s+оплат\w*",
        r"\bзаказчик\s+(?:осуществляет|производит|перечисляет)\s+оплат\w*",
        r"\bоплат\w*\s+(?:осуществляется|производится|перечисляется)",
        r"\bоплат\w*\s+(?:после|в течение|по факту|на основании)",
    )
    if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in grounded_markers):
        return "Проект контракта содержит условия оплаты."
    return None


def _local_xml_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return html.unescape(" ".join(part.strip() for part in node.itertext() if part.strip()))


def _first_xml_descendant(node: ET.Element, names: set[str]) -> ET.Element | None:
    lowered = {name.lower() for name in names}
    return next(
        (candidate for candidate in node.iter() if _local_xml_name(candidate.tag).lower() in lowered),
        None,
    )


def _structured_okpd2(node: ET.Element) -> str | None:
    direct = _first_xml_descendant(node, {"OKPDCode", "OKPD2Code", "okpdCode"})
    if direct is not None:
        value = _xml_text(direct).strip()
        if re.fullmatch(r"\d{2}(?:\.\d{1,3}){1,4}", value):
            return value
    for candidate in node.iter():
        if _local_xml_name(candidate.tag).lower() not in {"okpd2", "okpd2info", "okpd"}:
            continue
        code = _first_xml_descendant(candidate, {"OKPDCode", "OKPD2Code", "code"})
        value = _xml_text(code).strip()
        if re.fullmatch(r"\d{2}(?:\.\d{1,3}){1,4}", value):
            return value
    return None


def _structured_ktru(node: ET.Element) -> str | None:
    ktru = _first_xml_descendant(node, {"KTRU"})
    if ktru is None:
        return None
    code = _first_xml_descendant(ktru, {"code", "KTRUCode"})
    value = _xml_text(code).strip()
    return value or None


def _structured_purchase_object_name(node: ET.Element) -> tuple[str, str]:
    for child in node:
        if _local_xml_name(child.tag).lower() in {"name", "purchaseobjectinfo", "objectname", "productname"}:
            value = _legacy._normalize_supply_name(_xml_text(child))
            if value:
                return value, f"purchaseObject/{_local_xml_name(child.tag)}"
    for tag in ("purchaseObjectInfo", "objectName", "productName"):
        candidate = _first_xml_descendant(node, {tag})
        value = _legacy._normalize_supply_name(_xml_text(candidate))
        if value:
            return value, f"purchaseObject/{tag}"
    ktru = _first_xml_descendant(node, {"KTRU"})
    candidate = _first_xml_descendant(ktru, {"name"}) if ktru is not None else None
    value = _legacy._normalize_supply_name(_xml_text(candidate))
    return (value, "purchaseObject/KTRU/name") if value else ("", "")


def _structured_quantity(node: ET.Element) -> str | None:
    quantity = next(
        (child for child in node if _local_xml_name(child.tag).lower() in {"quantity", "count", "amount"}),
        None,
    )
    if quantity is None:
        quantity = _first_xml_descendant(node, {"quantity", "count"})
    if quantity is None:
        return None
    value_node = _first_xml_descendant(quantity, {"value", "concreteValue"})
    raw = _xml_text(value_node or quantity)
    return _legacy._normalize_quantity_value(raw) if re.search(r"\d", raw) else None


def _structured_unit(node: ET.Element) -> str | None:
    okei = _first_xml_descendant(node, {"OKEI", "manualUserOKEI"})
    if okei is None:
        return None
    value = _xml_text(_first_xml_descendant(okei, {"nationalCode", "name"}))
    return _legacy._normalize_supply_unit(value or None)


def _extract_supply_items_from_notification_xml(text: str, source_document: str) -> list[Any]:
    """Preserve legacy rows and recover source-backed EIS purchase-object fields.

    The legacy parser remains authoritative where it succeeds.  This wrapper
    enriches its rows with explicit OKPD2 and admits a structured purchaseObject
    without a per-row price when name plus quantity/unit/OKPD2 are present.  A
    contract-level NMCK is not a valid reason to discard the purchase object.
    """

    legacy_rows = list(_ORIGINAL_EXTRACT_SUPPLY_ITEMS_FROM_NOTIFICATION_XML(text, source_document))
    if not text or "purchaseobject" not in text.lower():
        return legacy_rows
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return legacy_rows

    objects = [node for node in root.iter() if _local_xml_name(node.tag).lower() == "purchaseobject"]
    rows_by_number = {
        int(row.source_row_number): row
        for row in legacy_rows
        if getattr(row, "source_row_number", None) is not None
    }
    recovered = list(legacy_rows)
    for row_number, node in enumerate(objects, start=1):
        okpd2 = _structured_okpd2(node)
        ktru = _structured_ktru(node)
        existing = rows_by_number.get(row_number)
        if existing is not None:
            if okpd2 and not getattr(existing, "okpd2", None):
                existing.okpd2 = okpd2
            if ktru and not getattr(existing, "ktru", None):
                existing.ktru = ktru
            continue

        name, name_path = _structured_purchase_object_name(node)
        quantity = _structured_quantity(node)
        unit = _structured_unit(node)
        if not name or not any((quantity, unit, okpd2, ktru)):
            continue
        type_node = _first_xml_descendant(node, {"type"})
        item_type = "service" if _xml_text(type_node).upper() in {"SERVICE", "WORK"} else "goods"
        price = _legacy._parse_float(_xml_text(_first_xml_descendant(node, {"price", "unitPrice"})))
        total = _legacy._parse_float(_xml_text(_first_xml_descendant(node, {"sum", "totalPrice"})))
        evidence_seed = f"{source_document}|notification-xml|{row_number}|{name}".encode("utf-8")
        recovered.append(
            SupplyItem(
                item_no=None,
                name=name,
                quantity=quantity,
                unit=unit,
                characteristics=[],
                gost=_legacy._extract_gost_tokens(_xml_text(node)),
                equivalent_allowed=None,
                source_document=source_document,
                source_kind="notification_xml",
                confidence="high",
                raw_fragment=_xml_text(node),
                unit_price=_legacy._format_decimal_price(price),
                total_price=_legacy._format_decimal_price(total),
                source_documents=[source_document],
                item_type=item_type,
                quantity_status="specified" if quantity is not None and unit else "not_specified",
                pricing_basis="unit_price" if price is not None else "unknown",
                source_row_number=row_number,
                evidence_id=f"ev-{hashlib.sha256(evidence_seed).hexdigest()[:16]}",
                unit_original=unit,
                ktru=ktru,
                okpd2=okpd2,
                name_source_type="structured_direct_name",
                name_source_path=name_path,
                quantity_source_path="purchaseObject/quantity" if quantity is not None else None,
                unit_source_path="purchaseObject/OKEI" if unit is not None else None,
                extraction_strategy="notification_xml_purchase_object",
            )
        )
    recovered.sort(key=lambda row: (getattr(row, "source_row_number", None) or 10**9, row.name.lower()))
    return recovered


def _enrich_procurement_metadata_from_documents(
    metadata: dict[str, Any], **kwargs: Any
) -> dict[str, Any]:
    """Recover EIS structured metadata from preserved XML text for R10.1.

    Uploaded-demo documents may still carry ``raw_content`` and are handled by
    the legacy path first.  Persisted application inputs intentionally do not
    retain raw bytes; for those, parse the deterministic XML text projection and
    fill only fields that remain absent after the legacy enrichment.
    """

    enriched = _ORIGINAL_ENRICH_PROCUREMENT_METADATA_FROM_DOCUMENTS(metadata, **kwargs)
    documents = list(kwargs.get("documents") or [])
    if not documents:
        return enriched

    from src.modules.tender_operator_agent_demo.eis_notice_parser import (
        apply_structured_metadata_to_procurement,
        extract_notice_metadata,
        merge_structured_metadata,
    )

    candidates: list[tuple[int, dict[str, Any]]] = []
    for document in documents:
        if str(getattr(document, "extension", "")).lower() != ".xml":
            continue
        text = str(getattr(document, "text", "") or "").strip()
        if not text.startswith("<"):
            continue
        parsed = extract_notice_metadata(text)
        if not parsed:
            continue
        score = sum(
            1
            for key in (
                "nmck",
                "okpd2_codes",
                "procurement_subject",
                "customer_name",
                "submission_deadline",
                "publication_date",
            )
            if parsed.get(key) not in (None, "", [])
        )
        if getattr(document, "role", "") == "notice":
            score += 10
        candidates.append((score, parsed))
    if not candidates:
        return enriched

    _, notice_meta = max(candidates, key=lambda item: item[0])
    structured = merge_structured_metadata(notice_meta, {}, {})
    existing_procurement = (
        dict(enriched.get("procurement"))
        if isinstance(enriched.get("procurement"), dict)
        else {}
    )
    candidate_procurement = dict(existing_procurement)
    apply_structured_metadata_to_procurement(candidate_procurement, structured)
    for key, value in candidate_procurement.items():
        current = existing_procurement.get(key)
        if current in (None, "", [], {}):
            existing_procurement[key] = value
    enriched["procurement"] = existing_procurement

    root_map = {
        "initial_price": "initial_price",
        "okpd2_codes": "okpd2_codes",
        "customer_name": "customer_name",
        "customer_inn": "customer_inn",
        "customer_kpp": "customer_kpp",
        "delivery_place": "delivery_place",
        "publication_date": "publication_date",
        "deadline": "deadline",
        "procedure_type": "procedure_type",
    }
    for procurement_key, root_key in root_map.items():
        value = existing_procurement.get(procurement_key)
        if enriched.get(root_key) in (None, "", [], {}) and value not in (None, "", [], {}):
            enriched[root_key] = value
    return enriched


def _build_preliminary_procurement_analysis(**kwargs: Any) -> dict[str, Any]:
    """Preserve legacy extraction and enrich only the R10.1 customer path."""

    result = _ORIGINAL_BUILD_PRELIMINARY_PROCUREMENT_ANALYSIS(**kwargs)
    metadata = kwargs.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("analysis_mode") != (
        "production_llm_r10_1"
    ):
        return result

    contract_text = str(kwargs.get("contract_draft_text") or "")
    existing = [str(item) for item in result.get("contract_highlights", []) if item]
    normalized = {" ".join(item.lower().split()) for item in existing}
    for highlight in (
        _payment_contract_highlight(contract_text),
        _liability_contract_highlight(contract_text),
    ):
        if not highlight:
            continue
        key = " ".join(highlight.lower().split())
        if key not in normalized:
            existing.append(highlight)
            normalized.add(key)
    result["contract_highlights"] = existing[:8]
    return result


_legacy._extract_supply_items_from_notification_xml = (
    _extract_supply_items_from_notification_xml
)
_legacy._enrich_procurement_metadata_from_documents = (
    _enrich_procurement_metadata_from_documents
)
_legacy._build_preliminary_procurement_analysis = (
    _build_preliminary_procurement_analysis
)


def _is_r10_1_model(model: dict[str, Any]) -> bool:
    provenance = model.get("ai_runtime_provenance")
    return bool(
        isinstance(provenance, dict)
        and provenance.get("producer") == "production_llm_r10_1"
    )


def _default_okpd2(model: dict[str, Any]) -> str | None:
    codes = model.get("okpd2_codes")
    if isinstance(codes, list):
        values = [
            str(item.get("code") or "").strip()
            for item in codes
            if isinstance(item, dict) and item.get("code")
        ]
        if values:
            return "; ".join(dict.fromkeys(values))
    passport = model.get("procurement_passport")
    if isinstance(passport, dict):
        value = str(passport.get("okpd2") or "").strip()
        if value and "не указан" not in value.lower():
            return value
    return None


def _render_customer_report_html(model: dict[str, Any]) -> str:
    """Render only the sanitized customer projection for R10.1."""

    from src.modules.tender_operator_agent_demo.customer_report_contract import (
        build_customer_detail_projection,
    )
    from src.modules.tender_operator_agent_demo.report_model import (
        build_customer_report_projection,
    )

    projection = build_customer_report_projection(model)
    detail = build_customer_detail_projection(model)
    default_okpd2 = _default_okpd2(model)

    def esc(value: Any) -> str:
        fallback = "Данных недостаточно — требуется проверка"
        return html.escape(str(value if value not in (None, "") else fallback))

    def bullets(values: list[Any]) -> str:
        return "".join(f"<li>{esc(value)}</li>" for value in values)

    def requirement_rows(values: list[dict[str, str]]) -> str:
        return "".join(
            "<tr>"
            f"<td>{esc(item.get('title'))}</td>"
            f"<td>{esc(item.get('detail') or '—')}</td>"
            f"<td>{esc(item.get('source'))}</td>"
            "</tr>"
            for item in values
        )

    decision = projection["customer_decision"]
    documents = "".join(
        f"<li>{esc(item['name'])} ({esc(item['type'])})</li>"
        for item in projection["customer_documents"]
    )
    rows = "".join(
        "<tr>"
        f"<td>{esc(row['sequence'])}</td>"
        f"<td>{esc(row['original_name'])}</td>"
        f"<td>{esc(row['quantity_display'])}</td>"
        f"<td>{esc(row['unit_original'])}</td>"
        f"<td>{esc(row.get('okpd2') or default_okpd2 or 'Не извлечён')}</td>"
        f"<td>{esc('; '.join(row.get('characteristics') or []) or '—')}</td>"
        f"<td>{esc(row['source_display'])}</td>"
        "</tr>"
        for row in projection["line_items"]
    )
    evidence = bullets(
        [
            f"{item['document_label']} — {item['document_type']}, {item['location']}"
            for item in projection["evidence_map"]
        ]
    )
    risks = bullets(
        [
            f"{risk.get('risk') or risk.get('description')}: {risk.get('impact')}. "
            f"Что сделать: {risk.get('mitigation')}"
            for risk in projection["risks"]
        ]
    )
    questions = [
        item.get("question") if isinstance(item, dict) else item
        for item in projection["customer_questions"]
    ]

    economics = ""
    if projection.get("unit_economics"):
        item = projection["unit_economics"]
        value = f"{item['value']:,.2f}".replace(",", " ").replace(".", ",")
        economics = (
            "<section><h2>Экономический ориентир</h2>"
            "<p>НМЦК, делённая на подтверждённый объём, составляет "
            f"ориентировочно <strong>{value} ₽ за {esc(item['unit'])}</strong>."
            "</p><p>Это арифметический ориентир по НМЦК, а не "
            "подтверждённая закупочная себестоимость.</p></section>"
        )

    as_of = ""
    if projection.get("analysis_as_of") not in (
        None,
        "",
        "Данных недостаточно — требуется проверка",
    ):
        as_of = (
            "<p>Отчёт сформирован по состоянию на: "
            f"{esc(projection['analysis_as_of'])}</p>"
        )

    items_section = ""
    if rows:
        technical_note = (
            "<p>Подробные требования приведены ниже в разделе «Технические требования».</p>"
            if detail["has_grounded_requirements"]
            else "<p>Детальные характеристики требуют дополнительной ручной проверки по документам.</p>"
        )
        items_section = (
            "<section><h2>Состав и объём закупки</h2><div class='scroll'>"
            "<table><thead><tr><th>№</th><th>Наименование</th>"
            "<th>Количество</th><th>Единица</th><th>ОКПД2</th>"
            "<th>Ключевые характеристики</th>"
            "<th>Подтверждённый источник</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>{technical_note}</section>"
        )

    requirement_sections = ""
    for title, key in (
        ("Технические требования", "technical_requirements"),
        ("Требования к заявке и участнику", "application_requirements"),
        ("Прочие подтверждённые требования", "other_requirements"),
    ):
        values = detail[key]
        if values:
            requirement_sections += (
                f"<section><h2>{esc(title)}</h2><div class='scroll'>"
                "<table><thead><tr><th>Требование</th><th>Деталь</th>"
                f"<th>Источник</th></tr></thead><tbody>{requirement_rows(values)}"
                "</tbody></table></div></section>"
            )

    contract_sections = ""
    if detail["contract_term_groups"]:
        groups = "".join(
            f"<h3>{esc(group['title'])}</h3><ul>{bullets(group['items'])}</ul>"
            for group in detail["contract_term_groups"]
        )
        contract_sections = f"<section><h2>Условия контракта</h2>{groups}</section>"

    risks_section = (
        f"<section><h2>Риски, подтверждённые документами</h2><ul>{risks}</ul></section>"
        if risks
        else ""
    )
    if questions:
        questions_section = (
            f"<section><h2>Вопросы для уточнения</h2><ul>{bullets(questions)}</ul></section>"
        )
    elif projection.get("document_set_complete"):
        questions_section = (
            "<section><h2>Вопросы для уточнения</h2>"
            "<p>Дополнительные вопросы по результатам анализа не сформированы.</p></section>"
        )
    else:
        questions_section = (
            "<section><h2>Вопросы для уточнения</h2>"
            "<p>Сначала необходимо получить недостающие документы, затем повторить анализ.</p></section>"
        )
    evidence_section = (
        f"<section><h2>Источники</h2><ul>{evidence}</ul></section>"
        if evidence
        else ""
    )
    limitations = projection["corpus_limitations"]
    limitations_section = (
        "<section><h2>Ограничения комплекта документов</h2><ul>"
        f"{bullets(limitations)}</ul></section>"
        if limitations
        else ""
    )

    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Анализ закупки № {esc(projection.get('procurement_number'))}</title><style>body{{margin:0;background:#f5f8fa;color:#10243e;font:16px Arial,sans-serif}}main{{max-width:1180px;margin:auto;padding:24px}}section{{background:#fff;border:1px solid #dce5eb;border-radius:12px;padding:20px;margin:16px 0}}h1,h2{{color:#003b5c}}.decision{{border-left:6px solid #d08300}}.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;min-width:860px}}th,td{{border-bottom:1px solid #dce5eb;padding:9px;text-align:left;vertical-align:top}}th{{background:#e9f7f5}}</style></head><body><main>
<section><h1>Анализ закупки № {esc(projection.get('procurement_number'))}</h1><p>Отчёт для принятия решения об участии</p><details><summary>Документы комплекта ({esc(projection['documents_count'])})</summary><ul>{documents}</ul></details></section>
<section><h2>{esc(projection.get('procurement_title'))}</h2><p>Заказчик: {esc(projection.get('customer_name'))}</p><p>Дата публикации: {esc(projection.get('publication_datetime_display'))}</p><p>Окончание подачи заявок: {esc(projection.get('application_deadline_display'))}</p><p>НМЦК: {esc(projection.get('nmck'))} ₽</p><p>Место поставки: {esc(projection.get('delivery_place'))}</p>{as_of}</section>
<section class="decision"><h2>Решение: {esc(decision.get('recommendation'))}</h2><h3>Ключевые основания</h3><ul>{bullets(decision.get('reasons', []))}</ul><h3>Подтверждено документами</h3><ul>{bullets(decision.get('confirmed', []))}</ul>{('<h3>Не удалось оценить</h3><ul>' + bullets(decision.get('not_evaluated', [])) + '</ul>') if decision.get('not_evaluated') else ''}<p><strong>Следующее действие:</strong> {esc(decision.get('next_action'))}</p></section>
{items_section}{economics}{requirement_sections}{contract_sections}<section><h2>Коммерческие предложения</h2><p>Коммерческие предложения не загружены; экономика участия не рассчитана.</p></section>{risks_section}{questions_section}{evidence_section}{limitations_section}</main></body></html>'''


def _render_canonical_report_html(model: dict[str, Any]) -> str:
    """Preserve legacy rendering, with R10.1 routed to the customer view."""

    if _is_r10_1_model(model):
        return _render_customer_report_html(model)
    return _legacy._render_product_report_html(model, customer=False)


def _persist_outputs(
    run_id: str,
    metadata: dict[str, Any],
    outputs: dict[str, dict[str, Any]],
    steps: list[Any],
) -> None:
    from src.modules.procurement_analysis.frozen_producer import (
        persist_frozen_r7_outputs,
    )

    renderer = (
        _render_customer_report_html
        if metadata.get("analysis_mode") == "production_llm_r10_1"
        else _render_canonical_report_html
    )
    persist_frozen_r7_outputs(
        output_dir=_legacy._output_dir(run_id),
        run_id=run_id,
        metadata=metadata,
        outputs=outputs,
        steps=steps,
        render_html=renderer,
        now_factory=_legacy._safe_datetime,
    )


_legacy._render_customer_report_html = _render_customer_report_html
_legacy._render_canonical_report_html = _render_canonical_report_html
_legacy._persist_outputs = _persist_outputs
