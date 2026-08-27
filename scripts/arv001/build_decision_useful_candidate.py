#!/usr/bin/env python3
"""Build a decision-useful ARV-001 candidate from the frozen real source corpus.

This corrective path intentionally performs no provider or EIS call. It binds to
an already accepted R10.1 canonical report, re-reads the immutable frozen source
files by SHA-256/size through the established ARV-001 corpus contract, extracts
concrete material terms deterministically, applies them to a derived in-memory
customer model, and writes a new Product-Owner candidate outside Git.

The accepted canonical file and frozen source bytes are read-only. A candidate
is emitted only when the decision-usefulness quality gate passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quality_gates.arv001.decision_usefulness import evaluate_decision_usefulness
from scripts.arv001.complete_corpus_contract import (
    DEFAULT_CORPUS_SHA256,
    DEFAULT_REGISTRY_NUMBER,
    AcceptanceBlocked,
    load_candidate,
    prepare_documents,
    sha256_file,
    validate_customer_report,
    validate_document_set,
)
from scripts.arv001.corpus_hash_resolver import resolve_corpus_hash_profile
from scripts.arv001.rework_human_report import (
    _read_canonical_report,
    _replace_decision_section,
    _replace_questions_with_checklist,
    _sanitize_raw_source_cells,
    _validate_customer_rework,
)
from scripts.arv001.run_complete_corpus_acceptance_split_roots import (
    build_ephemeral_candidate_view,
)
from src.modules.tender_operator_agent_demo.decision_useful_extraction import (
    material_detail_count,
)
from src.modules.tender_operator_agent_demo.decision_useful_extraction_v2 import (
    extract_decision_useful_analysis,
)
from src.modules.tender_operator_agent_demo.upload_service import (
    _render_customer_report_html,
)

DEFAULT_ACCEPTED_CANONICAL_SHA256 = (
    "3c3624115b7a8a77c91deaaf13d02f0b7cab019bbf74444512ed4c6b6646f09e"
)
_GENERIC_TECHNICAL_MARKERS = (
    "соответствие гост / ту",
    "соответствовать гост, ту",
    "соответствует гост, ту",
    "соответствовать гост, ту и иной",
)
_GENERIC_CONTRACT_MARKERS = (
    "проект контракта содержит условия оплаты",
    "проект контракта содержит условия ответственности",
    "проект контракта содержит условия о штрафах",
    "проект контракта содержит раздел об ответственности",
)
_CONTRACT_LABELS = {
    "payment": "Оплата",
    "security": "Обеспечение исполнения контракта",
    "acceptance": "Приёмка",
    "liability": "Ответственность / штрафы / пени",
    "termination": "Расторжение / односторонний отказ",
}
_FORBIDDEN_CUSTOMER_TEXT = (
    "Product Owner",
    "REPORT_REWORK_REQUIRED",
    "NOT_AUTHORIZED",
    "NOT_ALLOWED",
    "BLOCKED_EXTERNAL_SOURCE",
    "P8.05",
)


@dataclass(frozen=True)
class _DecisionDocument:
    role: str
    display_name: str
    text: str


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _outside_repo(path: Path, code: str) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    repo = _repo_root().resolve(strict=True)
    if resolved == repo or repo in resolved.parents:
        raise AcceptanceBlocked(code)
    return resolved


def _document_role(kind: str | None, name: str) -> str:
    value = f"{kind or ''} {name}".lower()
    if any(token in value for token in ("application", "заявк", "состав заявки")):
        return "application_requirements"
    if any(
        token in value
        for token in (
            "contract_performance_security",
            "performance_security",
            "обеспечени",
            "реквизиты",
        )
    ):
        return "contract_performance_security"
    if any(token in value for token in ("contract_draft", "draft_contract", "проект контракта", "проект договора")):
        return "contract_draft"
    if any(
        token in value
        for token in (
            "technical_spec",
            "technical specification",
            "техническ",
            "описание объекта",
            "спецификац",
        )
    ):
        return "technical_spec"
    if any(token in value for token in ("price_justification", "nmck", "нмцк")):
        return "price_justification"
    if any(token in value for token in ("notice", "notification", "извещ")):
        return "notice"
    return str(kind or "supporting")


def _decision_documents(prepared: list[Any]) -> list[_DecisionDocument]:
    return [
        _DecisionDocument(
            role=_document_role(item.document_kind, item.original_name),
            display_name=item.original_name,
            text=item.text,
        )
        for item in prepared
    ]


def _requirement_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        " ".join(str(row.get("title") or "").casefold().split()),
        " ".join(str(row.get("detail") or "").casefold().split()),
        " ".join(str(row.get("source") or "").casefold().split()),
    )


def _is_generic_technical_requirement(row: dict[str, Any]) -> bool:
    text = " ".join(
        str(row.get(key) or "") for key in ("title", "detail", "requirement", "name")
    ).casefold()
    return any(marker in text for marker in _GENERIC_TECHNICAL_MARKERS)


def _exact_contract_highlights(analysis: dict[str, Any]) -> list[str]:
    contract = analysis.get("contract") if isinstance(analysis.get("contract"), dict) else {}
    values: list[str] = []
    seen: set[str] = set()
    for key in ("payment", "security", "acceptance", "liability", "termination"):
        label = _CONTRACT_LABELS[key]
        for row in contract.get(key) or []:
            if not isinstance(row, dict) or not row.get("text"):
                continue
            text = " ".join(str(row["text"]).split())
            source = " ".join(str(row.get("source") or "Проект контракта").split())
            value = f"{label}: {text} Источник: {source}."
            identity = value.casefold()
            if identity not in seen:
                seen.add(identity)
                values.append(value)

    cap_rows = contract.get("liability_cap") or []
    for row in cap_rows:
        if not isinstance(row, dict) or not row.get("text"):
            continue
        source = " ".join(str(row.get("source") or "Проект контракта").split())
        value = f"Лимит штрафов / cap: {' '.join(str(row['text']).split())} Источник: {source}."
        if value.casefold() not in seen:
            seen.add(value.casefold())
            values.append(value)
    if not cap_rows and contract.get("liability_cap_status") == "not_found_in_processed_contract_text":
        values.append(
            "Лимит штрафов / cap: отдельное ограничение общей суммы штрафов "
            "не найдено в обработанном тексте проекта контракта."
        )
    return values


def derive_customer_model(
    canonical_model: dict[str, Any], analysis: dict[str, Any]
) -> dict[str, Any]:
    """Return a derived report model while leaving accepted canonical bytes intact."""

    model = deepcopy(canonical_model)
    technical = analysis.get("technical") if isinstance(analysis.get("technical"), dict) else {}
    exact_technical = bool(
        technical.get("standards") or technical.get("specific_clauses")
    )

    rows = [
        dict(item)
        for item in model.get("requirements", [])
        if isinstance(item, dict)
        and not (exact_technical and _is_generic_technical_requirement(item))
    ]
    seen = {_requirement_identity(row) for row in rows}
    additions: list[dict[str, str]] = []
    for standard in technical.get("standards") or []:
        additions.append(
            {
                "title": f"Стандарт / норматив: {standard}",
                "detail": str(standard),
                "type": "техническое требование",
                "source": "Техническое задание",
            }
        )
    for row in technical.get("specific_clauses") or []:
        if isinstance(row, dict) and row.get("text"):
            additions.append(
                {
                    "title": "Конкретная характеристика из ТЗ",
                    "detail": str(row["text"]),
                    "type": "техническое требование",
                    "source": str(row.get("source") or "Техническое задание"),
                }
            )
    for row in analysis.get("application_requirements") or []:
        if isinstance(row, dict) and row.get("text"):
            additions.append(
                {
                    "title": "Требование к заявке / участнику",
                    "detail": str(row["text"]),
                    "type": "требование к заявке",
                    "source": str(
                        row.get("source") or "Требования к составу заявки"
                    ),
                }
            )
    for row in additions:
        identity = _requirement_identity(row)
        if identity in seen:
            continue
        seen.add(identity)
        rows.append(row)
    model["requirements"] = rows

    compatibility = (
        deepcopy(model.get("compatibility_sections"))
        if isinstance(model.get("compatibility_sections"), dict)
        else {}
    )
    previous = [
        str(value)
        for value in compatibility.get("contract_highlights", [])
        if value
        and not any(marker in str(value).casefold() for marker in _GENERIC_CONTRACT_MARKERS)
        and not str(value).casefold().startswith(
            tuple(label.casefold() + ":" for label in _CONTRACT_LABELS.values())
            + ("лимит штрафов / cap:",)
        )
    ]
    compatibility["contract_highlights"] = [
        *_exact_contract_highlights(analysis),
        *previous,
    ][:40]
    model["compatibility_sections"] = compatibility
    return model


def render_decision_useful_report(
    model: dict[str, Any], *, expected_registry_number: str
) -> str:
    rendered = _render_customer_report_html(model)
    validate_customer_report(rendered, expected_registry_number)
    rendered = _replace_decision_section(model, rendered)
    rendered = _replace_questions_with_checklist(rendered)
    rendered = _sanitize_raw_source_cells(rendered)
    _validate_customer_rework(rendered)
    validate_customer_report(rendered, expected_registry_number)
    lowered = rendered.casefold()
    if any(marker.casefold() in lowered for marker in _FORBIDDEN_CUSTOMER_TEXT):
        raise AcceptanceBlocked("decision_useful_internal_governance_exposed")
    if "проект контракта содержит условия оплаты." in lowered:
        raise AcceptanceBlocked("decision_useful_generic_payment_flag_survived")
    return rendered


def _write_file(path: Path, data: bytes) -> None:
    path.write_bytes(data)
    os.chmod(path, 0o600)


def _publish_candidate(
    *,
    output_root: Path,
    html: str,
    analysis: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    if output_root.exists():
        raise AcceptanceBlocked("decision_useful_output_root_already_exists")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.partial.", dir=output_root.parent
        )
    )
    os.chmod(staging, 0o700)
    try:
        _write_file(
            staging / "upload-ready-report-decision-useful.html",
            html.encode("utf-8"),
        )
        _write_file(
            staging / "decision-useful-analysis.json",
            (json.dumps(analysis, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"),
        )
        _write_file(
            staging / "candidate-manifest.json",
            (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"),
        )
        os.replace(staging, output_root)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def build_candidate(
    *,
    canonical_output: Path,
    candidate_root: Path,
    intake_root: Path,
    output_root: Path,
    expected_registry_number: str = DEFAULT_REGISTRY_NUMBER,
    expected_corpus_sha: str = DEFAULT_CORPUS_SHA256,
    expected_canonical_sha: str = DEFAULT_ACCEPTED_CANONICAL_SHA256,
) -> dict[str, Any]:
    canonical_output = canonical_output.expanduser().resolve(strict=True)
    candidate_root = candidate_root.expanduser().resolve(strict=True)
    intake_root = intake_root.expanduser().resolve(strict=True)
    output_root = _outside_repo(
        output_root, "decision_useful_output_root_inside_repository"
    )
    if not candidate_root.is_dir() or not intake_root.is_dir():
        raise AcceptanceBlocked("decision_useful_frozen_source_root_missing")

    canonical_model, canonical_file_sha = _read_canonical_report(canonical_output)
    if canonical_file_sha != expected_canonical_sha:
        raise AcceptanceBlocked("decision_useful_accepted_canonical_sha_mismatch")
    canonical_bytes_before = canonical_output.read_bytes()
    canonical_model_before = _canonical_json_bytes(canonical_model)

    with tempfile.TemporaryDirectory(prefix="arv001-decision-useful-view-") as directory:
        view_root = Path(directory) / "candidate"
        build_ephemeral_candidate_view(
            candidate_root=candidate_root,
            intake_root=intake_root,
            view_root=view_root,
        )
        values, _shapes = load_candidate(view_root)
        physical = values["physical-files.json"]
        metadata = values["metadata.json"]
        if (
            not isinstance(physical, list)
            or len(physical) != 10
            or any(not isinstance(item, dict) for item in physical)
        ):
            raise AcceptanceBlocked("decision_useful_physical_files_contract_invalid")
        profile = resolve_corpus_hash_profile(physical, expected_corpus_sha)
        if profile.sha256 != expected_corpus_sha:
            raise AcceptanceBlocked("decision_useful_corpus_sha_mismatch")
        validate_document_set(values, 10)

        from src.shared.config.settings import get_settings

        settings = get_settings()
        prepared = prepare_documents(
            physical=physical,
            metadata=metadata,
            intake_root=intake_root,
            max_chars=settings.document_extract_max_chars,
            chunk_size=settings.rag_chunk_size_chars,
            chunk_overlap=settings.rag_chunk_overlap_chars,
        )
        if len(prepared) != 10:
            raise AcceptanceBlocked("decision_useful_prepared_document_count_invalid")
        source_identity_before = {
            item.original_name: {
                "sha256": item.sha256,
                "size_bytes": item.size_bytes,
            }
            for item in prepared
        }

        documents = _decision_documents(prepared)
        analysis = extract_decision_useful_analysis(documents)
        document_summary = values["document-set-summary.json"]
        gate = evaluate_decision_usefulness(analysis, document_summary)
        if gate.get("status") != "PASS":
            blockers = gate.get("blockers") or []
            code = ",".join(str(item) for item in blockers[:12])
            raise AcceptanceBlocked(
                "decision_usefulness_gate_failed:" + (code or "unknown")
            )

        derived_model = derive_customer_model(canonical_model, analysis)
        html = render_decision_useful_report(
            derived_model, expected_registry_number=expected_registry_number
        )

        # Source bytes and accepted canonical evidence remain immutable.
        source_identity_after = {
            item.original_name: {
                "sha256": sha256_file(item.path),
                "size_bytes": item.path.stat().st_size,
            }
            for item in prepared
        }
        if source_identity_after != source_identity_before:
            raise AcceptanceBlocked("decision_useful_source_bytes_mutated")
        if canonical_output.read_bytes() != canonical_bytes_before:
            raise AcceptanceBlocked("decision_useful_accepted_canonical_file_mutated")
        if _canonical_json_bytes(canonical_model) != canonical_model_before:
            raise AcceptanceBlocked("decision_useful_accepted_canonical_model_mutated")

    report_sha = _sha256_bytes(html.encode("utf-8"))
    analysis_bytes = json.dumps(
        analysis, ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8") + b"\n"
    manifest: dict[str, Any] = {
        "schema_version": "arv001-decision-useful-candidate-v1",
        "task": "ARV-001",
        "status": "decision_useful_candidate_for_product_owner_review",
        "registry_number": expected_registry_number,
        "accepted_canonical_sha256": canonical_file_sha,
        "frozen_corpus_sha256": expected_corpus_sha,
        "physical_document_count": 10,
        "logical_document_count": 6,
        "decision_usefulness_gate": gate,
        "material_detail_count": material_detail_count(analysis),
        "report_sha256": report_sha,
        "analysis_sha256": _sha256_bytes(analysis_bytes),
        "provider_calls_performed": False,
        "eis_requests_performed": False,
        "quality_acceptance_rerun": False,
        "accepted_canonical_mutated": False,
        "frozen_source_bytes_mutated": False,
        "production_db_mutations": 0,
        "git_mutations": 0,
        "product_owner": "REJECTED",
        "required_action": "DECISION_USEFUL_REPORT_REVIEW_REQUIRED",
        "independent_review": "NOT_AUTHORIZED",
        "freeze": "NOT_ALLOWED",
        "p805_status": "BLOCKED_EXTERNAL_SOURCE",
    }
    _publish_candidate(
        output_root=output_root,
        html=html,
        analysis=analysis,
        manifest=manifest,
    )
    return manifest


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build an ARV-001 decision-useful customer candidate from frozen "
            "source bytes without provider/EIS calls."
        )
    )
    parser.add_argument("--canonical-output", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--intake-root", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--expected-registry-number", default=DEFAULT_REGISTRY_NUMBER
    )
    parser.add_argument("--expected-corpus-sha", default=DEFAULT_CORPUS_SHA256)
    parser.add_argument(
        "--expected-canonical-sha", default=DEFAULT_ACCEPTED_CANONICAL_SHA256
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    candidate_root = args.candidate_root.expanduser().resolve()
    intake_root = (args.intake_root or candidate_root).expanduser().resolve()
    result = build_candidate(
        canonical_output=args.canonical_output,
        candidate_root=candidate_root,
        intake_root=intake_root,
        output_root=args.output_root,
        expected_registry_number=args.expected_registry_number,
        expected_corpus_sha=args.expected_corpus_sha,
        expected_canonical_sha=args.expected_canonical_sha,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "marker": "ARV001_DECISION_USEFUL_CANDIDATE_READY",
                "report_sha256": result["report_sha256"],
                "material_detail_count": result["material_detail_count"],
                "decision_usefulness_gate": result["decision_usefulness_gate"]["status"],
                "provider_calls_performed": False,
                "eis_requests_performed": False,
                "accepted_canonical_mutated": False,
                "frozen_source_bytes_mutated": False,
                "product_owner": "REJECTED",
                "independent_review": "NOT_AUTHORIZED",
                "freeze": "NOT_ALLOWED",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
