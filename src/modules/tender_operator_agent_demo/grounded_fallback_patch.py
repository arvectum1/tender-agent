"""Source-bound deterministic fallback hardening for PILOT-001-D04.

The operational pilot showed that the deterministic adapter could emit generic
goods/software assumptions as if they were procurement facts.  Install this
compatibility patch after the existing decision-usefulness layers and before
public facades capture legacy callables.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from src.modules.tender_operator_agent_demo import upload_service_legacy as _legacy


_INSTALLED = False
_ORIGINAL_PRELIMINARY = _legacy._build_preliminary_procurement_analysis
_ORIGINAL_GOODS_REQUIREMENTS = _legacy._build_goods_requirement_rows
_ORIGINAL_GOODS_RFQ = _legacy._build_goods_rfq_payload
_ORIGINAL_GOODS_ECONOMICS = _legacy._build_goods_economics_payload

_THEMES: dict[str, tuple[str, ...]] = {
    "delivery_deadline": (
        r"\b\d+\s+(?:рабоч(?:их|ие)|календарн(?:ых|ые))\s+дн",
        r"срок(?:и|ом)?\s+(?:поставк|отгрузк|исполнен)",
        r"поставк[аи]\s+по\s+заявк",
    ),
    "delivery_logistics": (r"\bдоставк",),
    "unloading": (r"разгруз",),
    "packaging": (r"упаков",),
    "stock": (r"наличи[ея]\s+(?:товар|на\s+склад)", r"складск"),
    "quality_documents": (
        r"сертифик",
        r"декларац",
        r"паспорт(?:а|ы)?\s+качеств",
        r"документ\w*\s+качеств",
    ),
    "normative": (r"\bгост\b", r"\bту\b", r"нормативн"),
    "analog": (r"аналог", r"эквивалент"),
    "manufacturer": (r"производител", r"страна\s+происхожд"),
    "service_resources": (r"специалист", r"ремонтн\w*\s+баз", r"оборудован"),
    "spare_parts": (r"запасн\w*\s+част", r"расходн\w*\s+материал"),
    "software": (
        r"программн",
        r"интеграц",
        r"\bсмэв\b",
        r"лиценз",
        r"модул",
        r"информационн\w*\s+систем",
    ),
}

_LABELS = {
    "delivery_deadline": "срок исполнения/поставки",
    "delivery_logistics": "условия доставки",
    "unloading": "разгрузка",
    "packaging": "упаковка",
    "stock": "складской остаток/наличие",
    "quality_documents": "документы качества",
    "normative": "ГОСТ/ТУ и нормативные требования",
    "analog": "допустимость аналогов/эквивалентов",
    "manufacturer": "производитель/страна происхождения",
    "service_resources": "специалисты/оборудование/ресурсная база",
    "spare_parts": "запасные части/расходные материалы",
    "software": "программная доработка/интеграции/лицензирование",
}

_GOODS_MATERIAL = {
    "delivery_deadline",
    "delivery_logistics",
    "unloading",
    "packaging",
    "stock",
    "quality_documents",
    "normative",
    "analog",
    "manufacturer",
}
_SERVICE_MATERIAL = {"delivery_deadline", "service_resources", "spare_parts"}
_WORKS_MATERIAL = {"delivery_deadline", "service_resources", "software"}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _source_corpus(
    documents: Iterable[Any],
    *extra_texts: str,
) -> str:
    parts = [_clean(getattr(document, "text", "")) for document in documents]
    parts.extend(_clean(text) for text in extra_texts)
    return "\n".join(part for part in parts if part).lower()


def _mentions(text: str, theme: str) -> bool:
    lowered = _clean(text).lower()
    return any(re.search(pattern, lowered, re.IGNORECASE) for pattern in _THEMES[theme])


def _supported(corpus: str, theme: str) -> bool:
    return any(re.search(pattern, corpus, re.IGNORECASE) for pattern in _THEMES[theme])


def _insufficient(theme_or_label: str) -> str:
    label = _LABELS.get(theme_or_label, theme_or_label)
    return f"INSUFFICIENT_EVIDENCE: {label} — первичные документы не подтверждают это условие."


def _category(procurement_kind: str | None) -> str:
    kind = (procurement_kind or "").lower()
    if kind == "goods":
        return "GOODS"
    if kind == "services":
        return "SERVICES"
    if kind in {"works", "mixed", "software_modification", "integration", "license"}:
        return "WORKS"
    return "SERVICES"


def _unsupported_themes(text: str, *, corpus: str, category: str) -> list[str]:
    applicable = {
        "GOODS": _GOODS_MATERIAL,
        "SERVICES": _SERVICE_MATERIAL,
        "WORKS": _WORKS_MATERIAL,
    }[category]
    unsupported: list[str] = []
    for theme in applicable:
        if _mentions(text, theme) and not _supported(corpus, theme):
            unsupported.append(theme)
    # Goods-only concepts must never leak into works/services unless evidence
    # explicitly contains them.
    if category != "GOODS":
        for theme in _GOODS_MATERIAL - {"delivery_deadline"}:
            if _mentions(text, theme) and not _supported(corpus, theme):
                unsupported.append(theme)
    # Software assumptions are permitted only when the evidence says software.
    if _mentions(text, "software") and not _supported(corpus, "software"):
        unsupported.append("software")
    return list(dict.fromkeys(unsupported))


def _ground_list(values: Iterable[Any], *, corpus: str, category: str) -> list[str]:
    grounded: list[str] = []
    insufficient_seen: set[str] = set()
    for raw in values:
        text = _clean(raw)
        if not text:
            continue
        unsupported = _unsupported_themes(text, corpus=corpus, category=category)
        if not unsupported:
            grounded.append(text)
            continue
        for theme in unsupported:
            if theme in insufficient_seen:
                continue
            grounded.append(_insufficient(theme))
            insufficient_seen.add(theme)
    return list(dict.fromkeys(grounded))


def _build_goods_requirement_rows(documents: list[Any]) -> list[dict[str, str]]:
    """Retain extracted item rows; drop fabricated generic requirement rows."""
    rows = _ORIGINAL_GOODS_REQUIREMENTS(documents)
    return [
        dict(row)
        for row in rows
        if _clean(row.get("source")).lower() != "техническое задание"
    ][:12]


def _build_goods_questions(documents: list[Any]) -> list[str]:
    corpus = _source_corpus(documents)
    items = _legacy._collect_goods_supply_items_from_documents(documents)
    questions = [
        f"Подтверждаете поставку {item.name} в объёме {item.quantity or 'не указано'} {item.unit or ''}?".strip()
        for item in items[:6]
    ]
    source_bound = (
        ("normative", "Уточните подтверждение требований ГОСТ/ТУ, указанных в документации."),
        ("quality_documents", "Уточните комплект документов качества, прямо требуемый документацией."),
        ("delivery_deadline", "Подтвердите срок поставки/исполнения, указанный в документации."),
        ("delivery_logistics", "Подтвердите условия доставки, указанные в документации."),
        ("unloading", "Подтвердите условие разгрузки, указанное в документации."),
        ("analog", "Уточните соответствие условиям об эквиваленте/аналоге из документации."),
        ("manufacturer", "Уточните сведения о производителе/стране происхождения, требуемые документацией."),
    )
    for theme, question in source_bound:
        if _supported(corpus, theme):
            questions.append(question)
    if not questions:
        questions.append(
            "INSUFFICIENT_EVIDENCE: товарные позиции и материальные коммерческие "
            "условия не извлечены; сначала сверить первичные документы."
        )
    return _legacy._dedupe_text_items(questions)


def _build_goods_rfq_payload(metadata: dict[str, Any], documents: list[Any]) -> dict[str, Any]:
    payload = dict(_ORIGINAL_GOODS_RFQ(metadata, documents))
    corpus = _source_corpus(documents)
    sections = ["Позиции поставки, количество и цена"]
    optional = (
        ("normative", "Требования ГОСТ/ТУ из документации"),
        ("quality_documents", "Документы качества из документации"),
        ("delivery_deadline", "Срок поставки/исполнения из документации"),
        ("delivery_logistics", "Условия доставки из документации"),
        ("unloading", "Условие разгрузки из документации"),
        ("analog", "Эквиваленты/аналоги в пределах условий документации"),
        ("manufacturer", "Производитель/страна происхождения по документации"),
    )
    for theme, section in optional:
        if _supported(corpus, theme):
            sections.append(section)
    payload["sections"] = sections
    payload["grounding_status"] = "source_bound"
    return payload


def _dedupe_metrics(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = repr(sorted((str(key), repr(value)) for key, value in item.items()))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _build_goods_economics_payload(
    metadata: dict[str, Any],
    documents: list[Any],
    analysis_mode: str,
    economics: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(
        _ORIGINAL_GOODS_ECONOMICS(metadata, documents, analysis_mode, economics)
    )
    corpus = _source_corpus(documents)
    payload["drivers"] = _ground_list(
        payload.get("drivers", []),
        corpus=corpus,
        category="GOODS",
    )
    payload["manual_checks"] = _ground_list(
        payload.get("manual_checks", []),
        corpus=corpus,
        category="GOODS",
    )
    metrics: list[dict[str, Any]] = []
    insufficient_seen: set[str] = set()
    for metric in payload.get("metrics", []):
        if not isinstance(metric, dict):
            continue
        candidate = f"{metric.get('label', '')}: {metric.get('value', '')}"
        unsupported = _unsupported_themes(
            candidate,
            corpus=corpus,
            category="GOODS",
        )
        if unsupported:
            for theme in unsupported:
                if theme in insufficient_seen:
                    continue
                metrics.append(
                    {"label": "Недостаточно данных", "value": _insufficient(theme)}
                )
                insufficient_seen.add(theme)
            continue
        copied = dict(metric)
        label = _clean(copied.get("label")).lower()
        if label == "общий объём":
            copied["label"] = "Подтверждённый объём позиций с единицей «м»"
        if "нмцк на метр" in label:
            copied["label"] = "Арифметический ориентир НМЦК на единицу «м»"
        metrics.append(copied)
    payload["metrics"] = _dedupe_metrics(metrics)
    payload["grounding_status"] = "source_bound"
    return payload


def _sanitize_overview(values: Iterable[Any], *, corpus: str, category: str) -> list[str]:
    grounded: list[str] = []
    for raw in values:
        text = _clean(raw)
        if not text:
            continue
        if (
            category == "GOODS"
            and re.search(r"общий\s+объ[её]м\s+кабел[яьи]/?провод", text, re.IGNORECASE)
            and not re.search(r"кабел|провод", corpus, re.IGNORECASE)
        ):
            match = re.search(r"([\d\s.,]+)\s*м\b", text)
            if match:
                grounded.append(
                    f"Подтверждённый объём позиций с единицей «м»: {_clean(match.group(1))} м."
                )
            continue
        unsupported = _unsupported_themes(
            text,
            corpus=corpus,
            category=category,
        )
        if unsupported:
            grounded.extend(_insufficient(theme) for theme in unsupported)
        else:
            grounded.append(text)
    return list(dict.fromkeys(grounded))


def _build_preliminary_procurement_analysis(
    *,
    metadata: dict[str, Any],
    documents: list[Any],
    technical_spec_text: str,
    contract_draft_text: str,
    notice_text: str,
) -> dict[str, Any]:
    result = dict(
        _ORIGINAL_PRELIMINARY(
            metadata=metadata,
            documents=documents,
            technical_spec_text=technical_spec_text,
            contract_draft_text=contract_draft_text,
            notice_text=notice_text,
        )
    )
    corpus = _source_corpus(
        documents,
        technical_spec_text,
        contract_draft_text,
        notice_text,
    )
    category = _category(result.get("procurement_kind"))
    result["overview"] = _sanitize_overview(
        result.get("overview", []),
        corpus=corpus,
        category=category,
    )
    for field in (
        "compliance_highlights",
        "delivery_model",
        "contract_highlights",
        "next_actions",
    ):
        result[field] = _ground_list(
            result.get(field, []),
            corpus=corpus,
            category=category,
        )

    # Generic works previously inherited a software-modification narrative.
    if category == "WORKS" and not _supported(corpus, "software"):
        result["compliance_highlights"] = [
            _insufficient("квалификационные и обязательные требования к исполнителю")
        ]
        result["delivery_model"] = [
            _insufficient("порядок и этапность выполнения работ")
        ]
        result["next_actions"] = [
            "Сверить предмет, объём, сроки и критерии приёмки работ по первичным документам.",
            _insufficient("ресурсные и специальные требования к исполнителю"),
        ]

    insufficient = [
        item
        for field in (
            "overview",
            "compliance_highlights",
            "delivery_model",
            "contract_highlights",
            "next_actions",
        )
        for item in result.get(field, [])
        if _clean(item).startswith("INSUFFICIENT_EVIDENCE:")
    ]
    result["grounded_fallback_category"] = category
    result["grounding_policy"] = "source_bound_v1"
    result["insufficient_evidence"] = list(dict.fromkeys(insufficient))
    return result


def install() -> None:
    """Install source-bound deterministic builders exactly once."""
    global _INSTALLED
    if _INSTALLED:
        return
    _legacy._build_goods_requirement_rows = _build_goods_requirement_rows
    _legacy._build_goods_questions = _build_goods_questions
    _legacy._build_goods_rfq_payload = _build_goods_rfq_payload
    _legacy._build_goods_economics_payload = _build_goods_economics_payload
    _legacy._build_preliminary_procurement_analysis = (
        _build_preliminary_procurement_analysis
    )
    _INSTALLED = True
