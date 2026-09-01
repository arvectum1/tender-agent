"""Finalize the ARV-001 PO candidate into an explicit human decision contract.

The decision-usefulness extraction/gate proves analytical depth. This finalizer
adds the human-facing contract required for actual decision use:

- explicit Decision / Evidence / Uncertainty / Caveats / Next action sections;
- deterministic evidence IDs for every factual claim used by the decision;
- explicit separation of measured/source facts from interpretation;
- deterministic HOLD behavior for uncertainty or detected contradictions;
- stale accepted-canonical protection before any final artifact is published.

No provider, EIS, RAG, acknowledgement, acceptance, DB, Git, or source-byte
mutation is performed. The candidate remains Product-Owner REJECTED until the
human Product Owner separately approves the generated artifact.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from scripts.arv001.complete_corpus_contract import (
    AcceptanceBlocked,
    validate_customer_report,
)
from scripts.arv001.rework_human_report import _deadline_assessment
from scripts.arv001.validate_decision_useful_candidate import (
    validate_rendered_material_terms,
)

_DECISION_SECTION_RE = re.compile(
    r'<section class="decision">.*?</section>', re.DOTALL
)
_ADVANCE_NEGATIVE_RE = re.compile(
    r"аванс\w*[^.\n]{0,120}?(?:не\s+предусмотр|не\s+устанавлива|отсутств)",
    re.IGNORECASE,
)
_ADVANCE_POSITIVE_RE = re.compile(
    r"(?:аванс\w*|предоплат\w*)[^.\n]{0,160}?\d+(?:[.,]\d+)?\s*%",
    re.IGNORECASE,
)
_SECURITY_NEGATIVE_RE = re.compile(
    r"обеспечени\w*[^.\n]{0,160}?(?:не\s+требуется|не\s+устанавлива|не\s+предусмотр)",
    re.IGNORECASE,
)
_SECURITY_POSITIVE_RE = re.compile(
    r"(?:обеспечени\w*|гарант\w*)[^.\n]{0,220}?"
    r"(?:\d+(?:[.,]\d+)?\s*%|\d[\d\s]*(?:[.,]\d+)?\s*руб|"
    r"независим\w*\s+гарант\w*|банковск\w*\s+гарант\w*)",
    re.IGNORECASE,
)
_SECURITY_SIZE_PLACEHOLDER_RE = re.compile(
    r"(?:размер\s+обеспечени\w*|обеспечени\w*.{0,120}?размер)"
    r".{0,420}?(?:_{2,}|(?:\.{3,}|…{2,}))\s*(?:руб\w*|%)",
    re.IGNORECASE,
)

_SECTIONS = (
    "Решение",
    "Доказательства",
    "Неопределённость",
    "Оговорки и ограничения",
    "Следующее действие",
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split()).strip()


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "\x1f".join(_normalize(part) for part in parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:16].upper()}"


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
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


def _row_locator(row: dict[str, Any]) -> tuple[int | None, int | None]:
    locator = row.get("locator")
    if not isinstance(locator, dict):
        return None, None
    try:
        start = int(locator.get("char_start"))
        end = int(locator.get("char_end"))
    except (TypeError, ValueError):
        return None, None
    return start, end


def _iter_material_rows(
    analysis: dict[str, Any],
) -> Iterable[tuple[str, str, dict[str, Any]]]:
    technical = analysis.get("technical")
    technical = technical if isinstance(technical, dict) else {}
    for row in technical.get("specific_clauses") or []:
        if isinstance(row, dict) and _normalize(row.get("text")):
            yield "technical", "Техническое требование", row

    contract = analysis.get("contract")
    contract = contract if isinstance(contract, dict) else {}
    labels = {
        "payment": "Оплата",
        "security": "Обеспечение исполнения контракта",
        "acceptance": "Приёмка",
        "liability": "Ответственность / штрафы / пени",
        "liability_cap": "Лимит ответственности",
        "termination": "Расторжение / односторонний отказ",
    }
    for key, label in labels.items():
        for row in contract.get(key) or []:
            if isinstance(row, dict) and _normalize(row.get("text")):
                yield f"contract.{key}", label, row

    for row in analysis.get("application_requirements") or []:
        if isinstance(row, dict) and _normalize(row.get("text")):
            yield "application", "Требование к заявке / участнику", row


def _material_evidence(
    analysis: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[str]]]:
    registry: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    by_category: dict[str, list[str]] = {}
    seen_ids: set[str] = set()

    technical = analysis.get("technical")
    technical = technical if isinstance(technical, dict) else {}
    for standard in technical.get("standards") or []:
        text = _normalize(standard)
        if not text:
            continue
        evidence_id = _stable_id(
            "ARV001-EV", "technical.standard", "Техническое задание", text
        )
        if evidence_id not in seen_ids:
            seen_ids.add(evidence_id)
            registry.append(
                {
                    "evidence_id": evidence_id,
                    "evidence_type": "normalized_source_fact",
                    "category": "technical.standard",
                    "source": "Техническое задание",
                    "text": text,
                    "locator": None,
                }
            )
            facts.append(
                {
                    "claim_id": _stable_id("ARV001-CL", "standard", text),
                    "claim_kind": "fact",
                    "category": "technical.standard",
                    "label": "Стандарт / норматив",
                    "text": text,
                    "evidence_ids": [evidence_id],
                }
            )
            by_category.setdefault("technical.standard", []).append(evidence_id)

    for category, label, row in _iter_material_rows(analysis):
        text = _normalize(row.get("text"))
        source = _normalize(row.get("source")) or "Документ закупки"
        start, end = _row_locator(row)
        evidence_id = _stable_id(
            "ARV001-EV", category, source, start, end, text
        )
        row["evidence_id"] = evidence_id
        row["evidence_ids"] = [evidence_id]
        if evidence_id not in seen_ids:
            seen_ids.add(evidence_id)
            registry.append(
                {
                    "evidence_id": evidence_id,
                    "evidence_type": "source_excerpt",
                    "category": category,
                    "source": source,
                    "text": text,
                    "locator": (
                        {"char_start": start, "char_end": end}
                        if start is not None and end is not None
                        else None
                    ),
                }
            )
        facts.append(
            {
                "claim_id": _stable_id("ARV001-CL", category, source, text),
                "claim_kind": "fact",
                "category": category,
                "label": label,
                "text": text,
                "evidence_ids": [evidence_id],
            }
        )
        by_category.setdefault(category, []).append(evidence_id)

    return registry, facts, by_category


def _canonical_deadline_evidence(
    canonical_model: dict[str, Any], canonical_sha: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = canonical_model.get("application_deadline")
    analysis_as_of = canonical_model.get("analysis_as_of_iso") or canonical_model.get(
        "analysis_as_of"
    )
    payload = {
        "application_deadline": deadline,
        "analysis_as_of": analysis_as_of,
    }
    evidence_id = _stable_id(
        "ARV001-EV",
        "accepted_canonical.deadline_state",
        canonical_sha,
        deadline,
        analysis_as_of,
    )
    evidence = {
        "evidence_id": evidence_id,
        "evidence_type": "accepted_canonical_fields",
        "category": "deadline_state",
        "source": "Принятый канонический результат анализа",
        "text": _normalize(json.dumps(payload, ensure_ascii=False, sort_keys=True)),
        "locator": {
            "artifact_sha256": canonical_sha,
            "fields": ["application_deadline", "analysis_as_of_iso|analysis_as_of"],
        },
    }
    fact = {
        "claim_id": _stable_id("ARV001-CL", "deadline_state", evidence_id),
        "claim_kind": "fact",
        "category": "deadline_state",
        "label": "Состояние срока подачи в принятом анализе",
        "text": evidence["text"],
        "evidence_ids": [evidence_id],
    }
    return evidence, fact


def _report_state_evidence(text: str) -> dict[str, Any]:
    clean = _normalize(text)
    evidence_id = _stable_id("ARV001-EV", "render_state", clean)
    return {
        "evidence_id": evidence_id,
        "evidence_type": "render_state",
        "category": "report_state",
        "source": "Сформированный отчёт",
        "text": clean,
        "locator": None,
    }


def _group_text(analysis: dict[str, Any], key: str) -> str:
    contract = analysis.get("contract")
    contract = contract if isinstance(contract, dict) else {}
    values = []
    for row in contract.get(key) or []:
        if isinstance(row, dict):
            values.append(_normalize(row.get("text")))
    return "\n".join(value for value in values if value)


def _contradictions(
    analysis: dict[str, Any], by_category: dict[str, list[str]]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    payment = _group_text(analysis, "payment")
    if _ADVANCE_NEGATIVE_RE.search(payment) and _ADVANCE_POSITIVE_RE.search(payment):
        result.append(
            {
                "code": "payment_advance_conflict",
                "text": "В извлечённых условиях оплаты одновременно обнаружены признаки отсутствия аванса и положительного размера аванса/предоплаты.",
                "evidence_ids": sorted(set(by_category.get("contract.payment", []))),
            }
        )
    security = _group_text(analysis, "security")
    if _SECURITY_NEGATIVE_RE.search(security) and _SECURITY_POSITIVE_RE.search(security):
        result.append(
            {
                "code": "performance_security_conflict",
                "text": "В извлечённых условиях обеспечения одновременно обнаружены признаки отсутствия обеспечения и конкретного размера/формы обеспечения.",
                "evidence_ids": sorted(set(by_category.get("contract.security", []))),
            }
        )
    return result


def build_human_decision_contract(
    *,
    canonical_model: dict[str, Any],
    canonical_sha: str,
    analysis: dict[str, Any],
    rendered_html: str,
) -> dict[str, Any]:
    registry, facts, by_category = _material_evidence(analysis)
    deadline_evidence, deadline_fact = _canonical_deadline_evidence(
        canonical_model, canonical_sha
    )
    registry.append(deadline_evidence)
    facts.insert(0, deadline_fact)
    by_category.setdefault("deadline_state", []).append(deadline_evidence["evidence_id"])

    recommendation, deadline_status, next_action = _deadline_assessment(canonical_model)
    uncertainties: list[dict[str, Any]] = []
    caveats: list[dict[str, Any]] = []

    deadline_ids = list(by_category["deadline_state"])
    if "не удалось подтвердить" in deadline_status.casefold():
        uncertainties.append(
            {
                "code": "deadline_not_confirmed",
                "text": deadline_status,
                "evidence_ids": deadline_ids,
            }
        )

    if "Коммерческие предложения не загружены" in rendered_html:
        report_evidence = _report_state_evidence(
            "Коммерческие предложения не загружены; экономика участия не рассчитана."
        )
        registry.append(report_evidence)
        uncertainties.append(
            {
                "code": "commercial_economics_not_calculated",
                "text": "Экономика участия не рассчитана, потому что коммерческие предложения не загружены.",
                "evidence_ids": [report_evidence["evidence_id"]],
            }
        )

    security_text = _group_text(analysis, "security")
    security_ids = sorted(set(by_category.get("contract.security", [])))
    if _SECURITY_SIZE_PLACEHOLDER_RE.search(security_text):
        if not security_ids:
            raise AcceptanceBlocked("human_decision_security_placeholder_without_evidence")
        uncertainties.append(
            {
                "code": "performance_security_amount_unresolved",
                "text": (
                    "В проекте контракта размер обеспечения исполнения не заполнен: "
                    "источник содержит шаблонное поле вместо конкретной суммы. "
                    "Финансовая нагрузка по обеспечению поэтому не определена по "
                    "зафиксированному комплекту документов."
                ),
                "evidence_ids": security_ids,
            }
        )
        if recommendation.startswith("HOLD"):
            next_action = (
                next_action.rstrip(". ")
                + ". Отдельно подтвердить конкретный размер обеспечения исполнения "
                "контракта и учесть стоимость гарантии либо отвлечения денежных средств."
            )

    conflicts = _contradictions(analysis, by_category)
    uncertainties.extend(conflicts)
    if conflicts:
        recommendation = "HOLD — устранить противоречия в существенных условиях закупки"
        next_action = (
            "Сверить противоречащие положения по исходным документам, зафиксировать "
            "однозначное условие и только после этого принимать решение об участии."
        )

    contract = analysis.get("contract")
    contract = contract if isinstance(contract, dict) else {}
    if contract.get("liability_cap_status") == "not_found_in_processed_contract_text":
        caveats.append(
            {
                "code": "liability_cap_not_found",
                "text": "Отдельный совокупный лимит штрафов/пеней не найден в обработанном тексте проекта контракта; отсутствие найденного условия не доказывает юридическое отсутствие ограничения.",
                "evidence_ids": sorted(
                    set(by_category.get("contract.liability", []))
                ),
            }
        )

    caveats.append(
        {
            "code": "frozen_corpus_scope",
            "text": "Выводы относятся к зафиксированному комплекту документов и моменту принятого анализа; изменения документов после этого момента этим запуском не подтверждаются.",
            "evidence_ids": deadline_ids,
        }
    )

    registry_by_id = {item["evidence_id"]: item for item in registry}
    for fact in facts:
        ids = fact.get("evidence_ids") or []
        if not ids or any(value not in registry_by_id for value in ids):
            raise AcceptanceBlocked("human_decision_fact_without_evidence")
    for item in [*uncertainties, *caveats]:
        ids = item.get("evidence_ids") or []
        if not ids or any(value not in registry_by_id for value in ids):
            raise AcceptanceBlocked("human_decision_uncertainty_without_evidence")

    if len(registry_by_id) < 2 or len(facts) < 2:
        raise AcceptanceBlocked("human_decision_material_evidence_missing")

    decision_ids = sorted(
        set(
            deadline_ids
            + by_category.get("contract.payment", [])
            + by_category.get("contract.security", [])
            + by_category.get("contract.acceptance", [])
            + by_category.get("contract.liability", [])
            + by_category.get("technical.standard", [])
            + by_category.get("technical", [])
        )
    )
    if not decision_ids:
        raise AcceptanceBlocked("human_decision_decision_evidence_missing")

    next_action_ids = sorted(
        set(
            decision_ids
            + [
                evidence_id
                for item in uncertainties
                for evidence_id in item.get("evidence_ids") or []
            ]
        )
    )

    return {
        "schema_version": "arv001-human-decision-contract-v1",
        "sections": list(_SECTIONS),
        "decision": {
            "claim_id": _stable_id("ARV001-CL", "decision", recommendation),
            "claim_kind": "interpretation",
            "text": recommendation,
            "evidence_ids": decision_ids,
        },
        "facts": facts,
        "uncertainty": uncertainties,
        "caveats": caveats,
        "next_action": {
            "claim_id": _stable_id("ARV001-CL", "next_action", next_action),
            "claim_kind": "recommendation",
            "text": next_action,
            "evidence_ids": next_action_ids,
        },
        "evidence_registry": sorted(
            registry_by_id.values(), key=lambda item: item["evidence_id"]
        ),
        "contradiction_count": len(conflicts),
        "uncertainty_count": len(uncertainties),
        "fact_count": len(facts),
        "evidence_count": len(registry_by_id),
    }


def _evidence_refs(values: list[str]) -> str:
    return ", ".join(f"<code>{html.escape(value)}</code>" for value in values)


def _render_contract(contract: dict[str, Any]) -> str:
    decision = contract["decision"]
    uncertainty = contract["uncertainty"]
    caveats = contract["caveats"]
    next_action = contract["next_action"]

    facts_html = "".join(
        "<li data-claim-kind=\"fact\" "
        f"data-evidence-ids=\"{html.escape(' '.join(item['evidence_ids']))}\">"
        f"<strong>Факт — {html.escape(item['label'])}:</strong> "
        f"{html.escape(item['text'])} "
        f"<span>Evidence ID: {_evidence_refs(item['evidence_ids'])}</span></li>"
        for item in contract["facts"]
    )
    uncertainty_html = (
        "".join(
            "<li data-claim-kind=\"uncertainty\" "
            f"data-evidence-ids=\"{html.escape(' '.join(item['evidence_ids']))}\">"
            f"{html.escape(item['text'])} "
            f"<span>Evidence ID: {_evidence_refs(item['evidence_ids'])}</span></li>"
            for item in uncertainty
        )
        or "<li>Существенных неопределённостей, влияющих на текущую рекомендацию, не выявлено в пределах проверенного корпуса.</li>"
    )
    caveats_html = "".join(
        "<li data-claim-kind=\"caveat\" "
        f"data-evidence-ids=\"{html.escape(' '.join(item['evidence_ids']))}\">"
        f"{html.escape(item['text'])} "
        f"<span>Evidence ID: {_evidence_refs(item['evidence_ids'])}</span></li>"
        for item in caveats
    )
    return (
        '<section class="decision" data-arv001-human-decision-contract="v1">'
        "<h2>Решение</h2>"
        f"<p data-claim-kind=\"interpretation\" data-evidence-ids=\"{html.escape(' '.join(decision['evidence_ids']))}\">"
        f"<strong>Предварительная рекомендация:</strong> {html.escape(decision['text'])}</p>"
        "<p><strong>Тип утверждения:</strong> интерпретация/рекомендация, а не измеренный факт. "
        f"<strong>Evidence ID:</strong> {_evidence_refs(decision['evidence_ids'])}</p>"
        "<h3>Доказательства</h3>"
        "<p>Ниже перечислены подтверждённые факты. Каждый факт связан со структурированным Evidence ID.</p>"
        f"<ul>{facts_html}</ul>"
        "<h3>Неопределённость</h3>"
        f"<ul>{uncertainty_html}</ul>"
        "<h3>Оговорки и ограничения</h3>"
        f"<ul>{caveats_html}</ul>"
        "<h3>Следующее действие</h3>"
        f"<p data-claim-kind=\"recommendation\" data-evidence-ids=\"{html.escape(' '.join(next_action['evidence_ids']))}\">"
        f"{html.escape(next_action['text'])}</p>"
        f"<p><strong>Evidence ID:</strong> {_evidence_refs(next_action['evidence_ids'])}</p>"
        "</section>"
    )


def _replace_decision(rendered_html: str, contract: dict[str, Any]) -> str:
    matches = list(_DECISION_SECTION_RE.finditer(rendered_html))
    if len(matches) != 1:
        raise AcceptanceBlocked("human_decision_existing_decision_section_invalid")
    replacement = _render_contract(contract)
    return _DECISION_SECTION_RE.sub(
        lambda _match: replacement, rendered_html, count=1
    )


def validate_human_decision_contract(
    rendered_html: str, contract: dict[str, Any]
) -> dict[str, Any]:
    for title in _SECTIONS:
        if title not in rendered_html:
            raise AcceptanceBlocked("human_decision_required_section_missing")
    if 'data-claim-kind="interpretation"' not in rendered_html:
        raise AcceptanceBlocked("human_decision_interpretation_not_marked")
    if 'data-claim-kind="fact"' not in rendered_html:
        raise AcceptanceBlocked("human_decision_fact_not_marked")

    evidence_ids = {
        item.get("evidence_id")
        for item in contract.get("evidence_registry") or []
        if isinstance(item, dict) and item.get("evidence_id")
    }
    if not evidence_ids:
        raise AcceptanceBlocked("human_decision_evidence_registry_empty")
    for section in ("decision", "next_action"):
        claim = contract.get(section)
        if not isinstance(claim, dict):
            raise AcceptanceBlocked("human_decision_claim_missing")
        ids = claim.get("evidence_ids") or []
        if not ids or any(value not in evidence_ids for value in ids):
            raise AcceptanceBlocked("human_decision_claim_without_evidence")
        if any(value not in rendered_html for value in ids):
            raise AcceptanceBlocked("human_decision_evidence_id_not_rendered")
    for fact in contract.get("facts") or []:
        if not isinstance(fact, dict):
            raise AcceptanceBlocked("human_decision_fact_invalid")
        ids = fact.get("evidence_ids") or []
        if not ids or any(value not in rendered_html for value in ids):
            raise AcceptanceBlocked("human_decision_fact_evidence_not_rendered")

    return {
        "status": "PASS",
        "sections": list(_SECTIONS),
        "evidence_count": len(evidence_ids),
        "fact_count": int(contract.get("fact_count") or 0),
        "uncertainty_count": int(contract.get("uncertainty_count") or 0),
        "contradiction_count": int(contract.get("contradiction_count") or 0),
        "decision_evidence_count": len(contract["decision"]["evidence_ids"]),
        "next_action_evidence_count": len(contract["next_action"]["evidence_ids"]),
    }


def finalize_candidate(
    *,
    output_root: Path,
    canonical_output: Path,
    expected_canonical_sha: str,
) -> dict[str, Any]:
    root = output_root.expanduser().resolve(strict=True)
    canonical_path = canonical_output.expanduser().resolve(strict=True)
    html_path = root / "upload-ready-report-decision-useful.html"
    analysis_path = root / "decision-useful-analysis.json"
    manifest_path = root / "candidate-manifest.json"

    try:
        original_html = html_path.read_text(encoding="utf-8")
        canonical_bytes = canonical_path.read_bytes()
    except (OSError, UnicodeError) as exc:
        raise AcceptanceBlocked("human_decision_required_artifact_unreadable") from exc
    analysis = _read_json(analysis_path, "human_decision_analysis_invalid")
    manifest = _read_json(manifest_path, "human_decision_manifest_invalid")
    canonical_sha = _sha256_bytes(canonical_bytes)
    if canonical_sha != expected_canonical_sha:
        raise AcceptanceBlocked("human_decision_stale_canonical_artifact")
    if manifest.get("accepted_canonical_sha256") != canonical_sha:
        raise AcceptanceBlocked("human_decision_manifest_canonical_mismatch")
    gate = manifest.get("decision_usefulness_gate")
    if not isinstance(gate, dict) or gate.get("status") != "PASS":
        raise AcceptanceBlocked("human_decision_requires_decision_usefulness_pass")
    try:
        canonical_model = json.loads(canonical_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceBlocked("human_decision_canonical_invalid") from exc
    if not isinstance(canonical_model, dict):
        raise AcceptanceBlocked("human_decision_canonical_invalid")

    enriched_analysis = deepcopy(analysis)
    contract = build_human_decision_contract(
        canonical_model=canonical_model,
        canonical_sha=canonical_sha,
        analysis=enriched_analysis,
        rendered_html=original_html,
    )
    final_html = _replace_decision(original_html, contract)
    registry_number = _normalize(manifest.get("registry_number"))
    if not registry_number:
        raise AcceptanceBlocked("human_decision_registry_number_missing")
    validate_customer_report(final_html, registry_number)
    validate_rendered_material_terms(final_html, enriched_analysis)
    contract_validation = validate_human_decision_contract(final_html, contract)

    enriched_analysis["human_decision_contract"] = contract
    analysis_bytes = (
        json.dumps(enriched_analysis, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    ).encode("utf-8")
    contract_bytes = (
        json.dumps(contract, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    html_bytes = final_html.encode("utf-8")

    final_manifest = deepcopy(manifest)
    final_manifest.update(
        {
            "schema_version": "arv001-decision-useful-candidate-v2",
            "status": "human_decision_contract_candidate_for_product_owner_review",
            "report_sha256": _sha256_bytes(html_bytes),
            "analysis_sha256": _sha256_bytes(analysis_bytes),
            "human_decision_contract_sha256": _sha256_bytes(contract_bytes),
            "human_decision_contract_status": "PASS",
            "human_decision_contract_validation": contract_validation,
            "human_decision_sections": list(_SECTIONS),
            "human_decision_evidence_count": contract["evidence_count"],
            "human_decision_fact_count": contract["fact_count"],
            "human_decision_uncertainty_count": contract["uncertainty_count"],
            "human_decision_contradiction_count": contract["contradiction_count"],
        }
    )
    manifest_bytes = (
        json.dumps(final_manifest, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    ).encode("utf-8")

    _atomic_write(html_path, html_bytes)
    _atomic_write(analysis_path, analysis_bytes)
    _atomic_write(root / "human-decision-contract.json", contract_bytes)
    _atomic_write(manifest_path, manifest_bytes)

    return {
        "status": "PASS",
        "report_sha256": final_manifest["report_sha256"],
        "analysis_sha256": final_manifest["analysis_sha256"],
        "human_decision_contract_sha256": final_manifest[
            "human_decision_contract_sha256"
        ],
        "validation": contract_validation,
        "decision": contract["decision"]["text"],
        "next_action": contract["next_action"]["text"],
        "evidence_count": contract["evidence_count"],
        "fact_count": contract["fact_count"],
        "uncertainty_count": contract["uncertainty_count"],
        "contradiction_count": contract["contradiction_count"],
    }
