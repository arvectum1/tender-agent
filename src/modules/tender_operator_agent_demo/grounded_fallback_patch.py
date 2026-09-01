"""Source-bound deterministic fallback hardening for PILOT-001-D04.

The operational pilot showed that deterministic fallback could emit generic
goods/software assumptions as if they were procurement facts. This layer runs
after the existing decision-usefulness patches and before public facades capture
legacy callables. It changes no external-action or LLM provenance boundary.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Iterable

from src.modules.tender_operator_agent_demo import upload_service_legacy as _legacy


_INSTALLED = False
# Capture these inside install(), after earlier compatibility layers are active.
_ORIGINAL_PRELIMINARY: Any = None
_ORIGINAL_OUTPUT_PAYLOADS: Any = None

_THEME_SPECS: dict[str, dict[str, tuple[str, ...]]] = {
    "delivery_deadline": {
        "detect": (
            r"срок[^.\n]{0,80}\b\d+\s+(?:рабоч(?:их|ие)|календарн(?:ых|ые))\s+дн",
            r"\b\d+\s+(?:рабоч(?:их|ие)|календарн(?:ых|ые))\s+дн[^.\n]{0,80}(?:постав|исполн|выполн|оказан|отгруз)",
            r"срок(?:и|ом)?\s+(?:поставк|отгрузк|исполнен|выполнен|оказан)",
            r"поставк[аи]\s+по\s+заявк",
        ),
        "evidence": (
            r"(?:срок(?:и)?\s+(?:поставк|отгрузк|исполнен|выполнен|оказан)|поставк[аи]\s+по\s+заявк)[^.\n]{0,160}",
            r"\b\d+\s+(?:рабоч(?:их|ие)|календарн(?:ых|ые))\s+дн[^.\n]{0,120}(?:постав|исполн|выполн|оказан|отгруз)",
        ),
    },
    "delivery_logistics": {
        "detect": (r"\bдоставк",),
        "evidence": (r"\bдоставк",),
    },
    "unloading": {"detect": (r"разгруз",), "evidence": (r"разгруз",)},
    "packaging": {"detect": (r"упаков",), "evidence": (r"упаков",)},
    "stock": {
        "detect": (r"складск", r"наличи[ея]\s+(?:товар|на\s+склад)"),
        "evidence": (r"складск", r"наличи[ея]\s+(?:товар|на\s+склад)"),
    },
    "certificate": {"detect": (r"сертифик",), "evidence": (r"сертифик",)},
    "declaration": {"detect": (r"декларац",), "evidence": (r"декларац",)},
    "quality_passport": {
        "detect": (r"паспорт(?:а|ы)?\s+качеств", r"документ\w*\s+качеств"),
        "evidence": (r"паспорт(?:а|ы)?\s+качеств", r"документ\w*\s+качеств"),
    },
    "gost": {
        "detect": (r"\bгост\b",),
        "evidence": (r"\bгост(?:\s|[-–—№]|\d)",),
    },
    "technical_conditions": {
        "detect": (r"\bту\b", r"техническ\w*\s+услов"),
        "evidence": (r"\bту\s+(?:\d|производител|на\s+)", r"техническ\w*\s+услов"),
    },
    "analog": {
        "detect": (r"аналог", r"эквивалент"),
        "evidence": (r"аналог", r"эквивалент"),
    },
    "manufacturer": {
        "detect": (r"производител",),
        "evidence": (r"производител",),
    },
    "origin_country": {
        "detect": (r"страна\s+происхожд",),
        "evidence": (r"страна\s+происхожд",),
    },
    "marking": {"detect": (r"маркиров",), "evidence": (r"маркиров",)},
    "safety": {"detect": (r"безопасност",), "evidence": (r"безопасност",)},
    "warranty": {"detect": (r"гаранти",), "evidence": (r"гаранти",)},
    "specialists": {
        "detect": (r"специалист",),
        "evidence": (r"специалист",),
    },
    "repair_base": {
        "detect": (r"ремонтн\w*\s+баз",),
        "evidence": (r"ремонтн\w*\s+баз",),
    },
    "performer_equipment": {
        "detect": (r"наличи[ея][^.\n]{0,40}оборудован", r"оборудован[^.\n]{0,60}исполнител"),
        "evidence": (r"наличи[ея][^.\n]{0,40}оборудован", r"оборудован[^.\n]{0,60}исполнител"),
    },
    "spare_parts": {
        "detect": (r"запасн\w*\s+част", r"расходн\w*\s+материал"),
        "evidence": (r"запасн\w*\s+част", r"расходн\w*\s+материал"),
    },
    "software": {"detect": (r"программн",), "evidence": (r"программн",)},
    "integration": {"detect": (r"интеграц",), "evidence": (r"интеграц",)},
    "module": {"detect": (r"\bмодул",), "evidence": (r"\bмодул",)},
    "license": {
        "detect": (r"лиценз", r"передач\w*\s+прав"),
        "evidence": (r"лиценз", r"передач\w*\s+прав"),
    },
    "medical": {
        "detect": (r"медицинск", r"\bсэмд\b", r"меддан"),
        "evidence": (r"медицинск", r"\bсэмд\b", r"меддан"),
    },
    "smev": {"detect": (r"\bсмэв\b",), "evidence": (r"\bсмэв\b",)},
    "ern": {"detect": (r"\bерн\b",), "evidence": (r"\bерн\b",)},
    "defense_data": {
        "detect": (r"минобороны", r"министерств\w*\s+обороны", r"витрин\w*\s+дан"),
        "evidence": (r"минобороны", r"министерств\w*\s+обороны", r"витрин\w*\s+дан"),
    },
    "drums": {"detect": (r"барабан",), "evidence": (r"барабан",)},
    "goods_supply": {
        "detect": (r"позици\w*\s+поставк", r"объ[её]м\s+поставк", r"поставляем\w*\s+товар"),
        "evidence": (r"позици\w*\s+поставк", r"объ[её]м\s+поставк", r"поставляем\w*\s+товар"),
    },
}

_THEME_LABELS = {
    "delivery_deadline": "срок исполнения/поставки",
    "delivery_logistics": "условия доставки",
    "unloading": "разгрузка",
    "packaging": "упаковка",
    "stock": "складской остаток/наличие",
    "certificate": "сертификаты",
    "declaration": "декларации",
    "quality_passport": "паспорт/документы качества",
    "gost": "ГОСТ",
    "technical_conditions": "ТУ/технические условия",
    "analog": "допустимость аналогов/эквивалентов",
    "manufacturer": "производитель",
    "origin_country": "страна происхождения",
    "marking": "маркировка",
    "safety": "требования безопасности",
    "warranty": "гарантийные условия",
    "specialists": "требования к специалистам",
    "repair_base": "ремонтная/ресурсная база",
    "performer_equipment": "оборудование исполнителя",
    "spare_parts": "запасные части/расходные материалы",
    "software": "программное обеспечение/доработка",
    "integration": "интеграционные требования",
    "module": "модуль/компонент системы",
    "license": "лицензирование/передача прав",
    "medical": "медицинская предметная область",
    "smev": "СМЭВ",
    "ern": "ЕРН",
    "defense_data": "данные/витрина Минобороны",
    "drums": "кабельные барабаны",
    "goods_supply": "товарные позиции/объём поставки",
}

_HARDCODED_GENERIC_REQUIREMENT_TITLES = {
    "соответствие гост / ту",
    "сертификаты и паспорт качества",
    "маркировка и безопасность",
    "доставка до заказчика",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _source_corpus(documents: Iterable[Any], *extra_texts: str) -> str:
    parts = [_clean(getattr(document, "text", "")) for document in documents]
    parts.extend(_clean(text) for text in extra_texts)
    return "\n".join(part for part in parts if part).lower()


def _category(procurement_kind: str | None) -> str:
    kind = (procurement_kind or "").lower()
    if kind == "goods":
        return "GOODS"
    if kind == "services":
        return "SERVICES"
    if kind in {"works", "mixed", "software_modification", "integration", "license"}:
        return "WORKS"
    return "SERVICES"


def _matches(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _mentioned_themes(text: str) -> list[str]:
    lowered = _clean(text).lower()
    return [
        theme
        for theme, spec in _THEME_SPECS.items()
        if _matches(lowered, spec["detect"])
    ]


def _evidence_supports(corpus: str, theme: str) -> bool:
    return _matches(corpus, _THEME_SPECS[theme]["evidence"])


def _unsupported_themes(text: str, *, corpus: str) -> list[str]:
    if _clean(text).startswith("INSUFFICIENT_EVIDENCE:"):
        return []
    return [
        theme
        for theme in _mentioned_themes(text)
        if not _evidence_supports(corpus, theme)
    ]


def _insufficient(theme_or_label: str) -> str:
    label = _THEME_LABELS.get(theme_or_label, theme_or_label)
    return (
        f"INSUFFICIENT_EVIDENCE: {label} — "
        "первичные документы не подтверждают это условие."
    )


def _ground_list(values: Iterable[Any], *, corpus: str) -> list[str]:
    grounded: list[str] = []
    seen_missing: set[str] = set()
    for raw in values:
        text = _clean(raw)
        if not text:
            continue
        unsupported = _unsupported_themes(text, corpus=corpus)
        if not unsupported:
            grounded.append(text)
            continue
        for theme in unsupported:
            if theme in seen_missing:
                continue
            grounded.append(_insufficient(theme))
            seen_missing.add(theme)
    return list(dict.fromkeys(grounded))


def _supporting_document_labels(documents: Iterable[Any], claim: str) -> list[str]:
    themes = _mentioned_themes(claim)
    labels: list[str] = []
    for document in documents:
        text = _clean(getattr(document, "text", "")).lower()
        if not text:
            continue
        if themes and all(_evidence_supports(text, theme) for theme in themes):
            label = _clean(getattr(document, "display_name", "")) or "source_document"
            labels.append(label)
    return list(dict.fromkeys(labels))


def _sanitize_preliminary(result: dict[str, Any], *, corpus: str) -> dict[str, Any]:
    category = _category(result.get("procurement_kind"))
    for field in (
        "overview",
        "compliance_highlights",
        "delivery_model",
        "contract_highlights",
        "next_actions",
    ):
        result[field] = _ground_list(result.get(field, []), corpus=corpus)

    overview: list[str] = []
    for text in result.get("overview", []):
        if (
            category == "GOODS"
            and re.search(r"общий\s+объ[её]м\s+кабел[яьи]/?провод", text, re.IGNORECASE)
            and not re.search(r"кабел|провод", corpus, re.IGNORECASE)
        ):
            match = re.search(r"([\d\s.,]+)\s*м\b", text)
            if match:
                overview.append(
                    "Подтверждённый объём позиций с единицей «м»: "
                    f"{_clean(match.group(1))} м."
                )
            continue
        overview.append(text)
    result["overview"] = list(dict.fromkeys(overview))

    software_themes = {
        "software",
        "integration",
        "module",
        "license",
        "medical",
        "smev",
        "ern",
        "defense_data",
    }
    if category == "WORKS" and not any(
        _evidence_supports(corpus, theme) for theme in software_themes
    ):
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
    corpus = _source_corpus(documents, technical_spec_text, contract_draft_text, notice_text)
    return _sanitize_preliminary(result, corpus=corpus)


def _sanitize_requirement_rows(
    rows: Iterable[Any],
    *,
    documents: list[Any],
    corpus: str,
) -> list[dict[str, Any]]:
    grounded: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        claim = f"{row.get('title', '')}. {row.get('detail', '')}"
        unsupported = _unsupported_themes(claim, corpus=corpus)
        generic_title = _clean(row.get("title")).lower()
        fake_generic_source = (
            _clean(row.get("source")).lower() == "техническое задание"
            and generic_title in _HARDCODED_GENERIC_REQUIREMENT_TITLES
        )
        if unsupported:
            continue
        if fake_generic_source:
            labels = _supporting_document_labels(documents, claim)
            if not labels:
                continue
            row["source"] = ", ".join(labels)
        grounded.append(row)
    return grounded


def _sanitize_economics(payload: dict[str, Any], *, corpus: str) -> dict[str, Any]:
    payload["drivers"] = _ground_list(payload.get("drivers", []), corpus=corpus)
    payload["manual_checks"] = _ground_list(payload.get("manual_checks", []), corpus=corpus)
    metrics: list[dict[str, Any]] = []
    missing_seen: set[str] = set()
    for raw in payload.get("metrics", []):
        if not isinstance(raw, dict):
            continue
        metric = dict(raw)
        candidate = f"{metric.get('label', '')}: {metric.get('value', '')}"
        unsupported = _unsupported_themes(candidate, corpus=corpus)
        if unsupported:
            for theme in unsupported:
                if theme in missing_seen:
                    continue
                metrics.append({"label": "Недостаточно данных", "value": _insufficient(theme)})
                missing_seen.add(theme)
            continue
        label = _clean(metric.get("label")).lower()
        if label == "общий объём":
            metric["label"] = "Подтверждённый объём позиций с единицей «м»"
        if "нмцк на метр" in label:
            metric["label"] = "Арифметический ориентир НМЦК на единицу «м»"
        metrics.append(metric)
    payload["metrics"] = metrics
    payload["grounding_status"] = "source_bound"
    return payload


def _sanitize_risks(payload: dict[str, Any], *, corpus: str) -> dict[str, Any]:
    risks: list[dict[str, Any]] = []
    missing_seen: set[str] = set()
    for raw in payload.get("risks", []):
        if not isinstance(raw, dict):
            continue
        risk = dict(raw)
        combined = " ".join(
            _clean(risk.get(key))
            for key in ("risk", "impact", "mitigation")
            if _clean(risk.get(key))
        )
        unsupported = _unsupported_themes(combined, corpus=corpus)
        if not unsupported:
            risks.append(risk)
            continue
        for theme in unsupported:
            if theme in missing_seen:
                continue
            risks.append(
                {
                    "risk": _insufficient(theme),
                    "severity": "needs_review",
                    "impact": "Материальный риск нельзя оценить без подтверждения первичным документом.",
                    "mitigation": "Проверить первичные документы вручную.",
                    "risk_id": f"insufficient-evidence-{theme}",
                    "category": "source_completeness",
                    "evidence_ids": [],
                    "evidence_locators": [],
                    "status": "requires_review",
                }
            )
            missing_seen.add(theme)
    payload["risks"] = risks or [
        {
            "risk": _insufficient("материальные риски"),
            "severity": "needs_review",
            "impact": "Недостаточно подтверждённых данных для предметного риск-вывода.",
            "mitigation": "Проверить первичные документы вручную.",
            "risk_id": "insufficient-evidence-material-risks",
            "category": "source_completeness",
            "evidence_ids": [],
            "evidence_locators": [],
            "status": "requires_review",
        }
    ]
    payload["manual_checks"] = _ground_list(payload.get("manual_checks", []), corpus=corpus)
    payload["summary"] = (
        "Риски ограничены утверждениями, подтверждёнными evidence; "
        "неподтверждённые материальные условия помечены INSUFFICIENT_EVIDENCE."
    )
    return payload


def _sanitize_fallback_outputs(
    outputs: dict[str, Any],
    *,
    documents: list[Any],
    corpus: str,
    category: str,
) -> dict[str, Any]:
    requirements = outputs.get("requirements")
    if isinstance(requirements, dict):
        requirements["requirements"] = _sanitize_requirement_rows(
            requirements.get("requirements", []),
            documents=documents,
            corpus=corpus,
        )
        context = requirements.get("analysis_context")
        if isinstance(context, dict):
            context["fallback_category"] = category
            context["grounding_policy"] = "source_bound_v1"

    questions = outputs.get("supplier_questions")
    if isinstance(questions, dict):
        questions["questions"] = _ground_list(questions.get("questions", []), corpus=corpus) or [
            _insufficient("вопросы поставщику")
        ]
        questions["ambiguities"] = _ground_list(questions.get("ambiguities", []), corpus=corpus)
        questions["grounding_status"] = "source_bound"

    rfq = outputs.get("rfq_draft")
    if isinstance(rfq, dict):
        rfq["sections"] = _ground_list(rfq.get("sections", []), corpus=corpus) or [
            _insufficient("секции RFQ")
        ]
        rfq["grounding_status"] = "source_bound"

    economics = outputs.get("economics")
    if isinstance(economics, dict):
        _sanitize_economics(economics, corpus=corpus)

    risks = outputs.get("contract_risks")
    if isinstance(risks, dict):
        _sanitize_risks(risks, corpus=corpus)

    recommendation = outputs.get("final_recommendation")
    if isinstance(recommendation, dict):
        recommendation["rationale"] = _ground_list(recommendation.get("rationale", []), corpus=corpus) or [
            _insufficient("основание рекомендации")
        ]
        if isinstance(requirements, dict):
            recommendation["key_requirements"] = [
                row.get("title", "")
                for row in requirements.get("requirements", [])[:4]
                if isinstance(row, dict) and row.get("title")
            ] or ["Проверка комплектности и evidence"]
        if isinstance(questions, dict):
            recommendation["open_questions"] = questions.get("questions", [])[:3]
        if isinstance(risks, dict):
            recommendation["risks"] = [
                row.get("risk", "")
                for row in risks.get("risks", [])[:4]
                if isinstance(row, dict) and row.get("risk")
            ]
        if isinstance(economics, dict):
            recommendation["economics"] = [
                f"{row.get('label')}: {row.get('value')}"
                for row in economics.get("metrics", [])
                if isinstance(row, dict)
            ]
        recommendation["grounding_status"] = "source_bound"
        recommendation["fallback_category"] = category

    trace = outputs.get("trace")
    if isinstance(trace, dict):
        if isinstance(recommendation, dict):
            trace["decision_factors"] = recommendation.get("rationale", [])
        trace["grounding_policy"] = "source_bound_v1"
        trace["fallback_category"] = category

    summary = outputs.get("tender_summary")
    if isinstance(summary, dict):
        summary["grounding_policy"] = "source_bound_v1"
        summary["fallback_category"] = category

    return outputs


def _build_output_payloads(
    *,
    metadata: dict[str, Any],
    documents: list[Any],
    analysis_mode: str,
    requirements: dict[str, Any],
    calibrated_risks: list[dict[str, Any]],
    supplier_questions: list[dict[str, Any]],
    tkp_comparison: dict[str, Any] | None,
    economics: dict[str, Any] | None,
    bid_decision: dict[str, Any] | None,
    core_complete: bool,
    quote_inputs_present: bool,
) -> dict[str, dict[str, Any]]:
    outputs = deepcopy(
        _ORIGINAL_OUTPUT_PAYLOADS(
            metadata=metadata,
            documents=documents,
            analysis_mode=analysis_mode,
            requirements=requirements,
            calibrated_risks=calibrated_risks,
            supplier_questions=supplier_questions,
            tkp_comparison=tkp_comparison,
            economics=economics,
            bid_decision=bid_decision,
            core_complete=core_complete,
            quote_inputs_present=quote_inputs_present,
        )
    )
    if analysis_mode != "fallback_deterministic_adapter":
        return outputs

    technical_spec_text = _legacy._collect_role_text(documents, "technical_spec")
    contract_draft_text = _legacy._collect_role_text(documents, "contract_draft")
    notice_text = (
        _legacy._collect_role_text(documents, "notice")
        or _legacy._collect_role_text(documents, "supporting")
        or _clean(metadata.get("tender_title"))
    )
    corpus = _source_corpus(documents, technical_spec_text, contract_draft_text, notice_text)
    preliminary = (
        outputs.get("requirements", {}).get("preliminary_analysis", {})
        if isinstance(outputs.get("requirements"), dict)
        else {}
    )
    category = _category(preliminary.get("procurement_kind") if isinstance(preliminary, dict) else None)
    return _sanitize_fallback_outputs(
        outputs,
        documents=documents,
        corpus=corpus,
        category=category,
    )


def install() -> None:
    """Install D04 source-bound wrappers exactly once."""
    global _INSTALLED
    global _ORIGINAL_PRELIMINARY
    global _ORIGINAL_OUTPUT_PAYLOADS
    if _INSTALLED:
        return
    _ORIGINAL_PRELIMINARY = _legacy._build_preliminary_procurement_analysis
    _ORIGINAL_OUTPUT_PAYLOADS = _legacy._build_output_payloads
    _legacy._build_preliminary_procurement_analysis = _build_preliminary_procurement_analysis
    _legacy._build_output_payloads = _build_output_payloads
    _INSTALLED = True
