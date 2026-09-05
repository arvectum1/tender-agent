#!/usr/bin/env python3
"""Prepare the first real BENCHMARK-PIPELINE-001 case without running the SUT.

This helper is intentionally Phase A only:

public 44-FZ card -> source/document intake -> copy exact source bytes ->
case_manifest.json -> source-only evaluator_bundle.json -> evaluator ZIP -> STOP

It MUST NOT call the Tender Agent analysis endpoint, render a report, freeze labels,
compare outputs, or create any SUT artifact. The independent evaluator receives the
ZIP and returns blind labels before Phase B is allowed to run.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_macmini_autonomous_procurement import (  # noqa: E402
    BackendClient,
    E2EBlocked,
    _auth_credentials_from_env,
    _registry_number,
)
from src.modules.benchmark_pipeline import (  # noqa: E402
    CONTRACT_VERSION,
    prepare_evaluator_bundle,
    source_bundle_sha256,
    verify_manifest_source_files,
    write_artifact,
)

DEFAULT_REGISTRY_NUMBER = "0848300045426000620"
FORBIDDEN_ANALYSIS_EVENTS = {
    "analysis_started",
    "analysis_completed",
    "llm_analysis_started",
    "llm_analysis_completed",
    "stub_analysis_fallback",
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _safe_name(value: str, fallback: str) -> str:
    name = Path(str(value or "")).name.strip()
    if not name or name in {".", ".."}:
        return fallback
    return name


def select_exact_card(cards: list[dict[str, Any]], registry_number: str) -> dict[str, Any]:
    exact = [
        card
        for card in cards
        if isinstance(card, dict) and _registry_number(card) == registry_number
    ]
    if not exact:
        discovered = sorted(
            {
                _registry_number(card)
                for card in cards
                if isinstance(card, dict) and _registry_number(card)
            }
        )
        raise E2EBlocked(
            "calibration_target_not_found",
            f"Public 44-FZ search did not return exact procurement {registry_number}.",
            details={"discovered_registry_numbers": discovered},
        )
    exact.sort(key=lambda item: str(item.get("publication_date") or ""), reverse=True)
    return exact[0]


def source_only_handoff(
    client: BackendClient,
    *,
    card: dict[str, Any],
    registry_number: str,
) -> dict[str, Any]:
    """Create an intake run while explicitly forbidding automatic analysis."""
    source_url = str(card.get("source_url") or "").strip()
    if not source_url:
        raise E2EBlocked(
            "missing_procurement_source_url",
            "Exact public procurement card has no source URL; calibration cannot preserve provenance.",
            details={"registry_number": registry_number},
        )
    payload = {
        "source": str(card.get("source") or "public_eis_html_44fz"),
        "law": "44fz",
        "reestr_number": registry_number,
        "source_url": source_url,
        "title": card.get("title"),
        "customer_name": card.get("customer_name"),
        "initial_price": card.get("initial_price"),
        "publication_date": card.get("publication_date"),
        "deadline": card.get("deadline"),
        "currency": card.get("currency") or "RUB",
        "status": card.get("status"),
        "procedure_type": card.get("procedure_type"),
        "download_archive": True,
        "analyze_after_download": False,
    }
    return client._json(
        "POST",
        "/api/demo/tender-agent/runs/from-search-result",
        payload=payload,
    )


def assert_source_only_run(run_payload: dict[str, Any]) -> None:
    mode = str(run_payload.get("analysis_mode") or "not_started")
    if mode != "not_started":
        raise E2EBlocked(
            "anti_circularity_analysis_already_started",
            "Calibration Phase A detected Tender Agent analysis before blind-label freeze.",
            details={"analysis_mode": mode},
        )
    if run_payload.get("final_recommendation") is not None:
        raise E2EBlocked(
            "anti_circularity_sut_output_present",
            "Calibration Phase A detected a Tender Agent recommendation before freeze.",
        )
    events = run_payload.get("events") or []
    event_types = {
        str(item.get("event_type") or "")
        for item in events
        if isinstance(item, dict)
    }
    forbidden = sorted(event_types & FORBIDDEN_ANALYSIS_EVENTS)
    if forbidden:
        raise E2EBlocked(
            "anti_circularity_analysis_event_present",
            "Calibration Phase A detected analysis events before blind-label freeze.",
            details={"events": forbidden},
        )


def _authorization_header(credentials: tuple[str, str] | None) -> str | None:
    if credentials is None:
        return None
    username, password = credentials
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _download_bytes(
    base_url: str,
    path: str,
    *,
    credentials: tuple[str, str] | None,
    timeout_seconds: int,
) -> bytes:
    headers = {"Accept": "application/octet-stream"}
    authorization = _authorization_header(credentials)
    if authorization:
        headers["Authorization"] = authorization
    request = Request(f"{base_url.rstrip('/')}{path}", headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - local operator URL by design
            return response.read()
    except HTTPError as exc:
        raise E2EBlocked(
            "source_file_download_http_error",
            f"Source-file endpoint returned HTTP {exc.code}.",
            details={"path": path, "status": exc.code},
        ) from exc
    except URLError as exc:
        raise E2EBlocked(
            "backend_unavailable",
            f"Tender Agent backend is unavailable while copying source bytes: {exc.reason}",
        ) from exc


def build_case_manifest(
    *,
    case_id: str,
    procurement: dict[str, Any],
    source_documents: list[dict[str, str]],
    acquired_at: str,
) -> dict[str, Any]:
    procurement_url = str(procurement.get("procurement_url") or "").strip()
    if not procurement_url:
        raise E2EBlocked(
            "missing_procurement_source_url",
            "Calibration run has no exact public procurement URL.",
        )
    documents = [
        {
            "path": item["path"],
            "sha256": item["sha256"],
            "source_url": item["source_url"],
        }
        for item in source_documents
    ]
    source_urls: list[str] = []
    for candidate in [procurement_url, *(item["source_url"] for item in documents)]:
        value = str(candidate or "").strip()
        if value and value not in source_urls:
            source_urls.append(value)
    if not source_urls:
        raise E2EBlocked("missing_source_url", "Calibration source bundle has no public source URL.")

    exact_attachment_provenance = all(
        item.get("provenance_kind") == "attachment_url" for item in source_documents
    )
    manifest = {
        "schema_version": CONTRACT_VERSION,
        "case_id": case_id,
        "procurement": {
            "notice_number": str(
                procurement.get("procurement_notice_number")
                or procurement.get("procurement_id")
                or ""
            ),
            "title": str(procurement.get("tender_title") or ""),
            "customer_name": str(procurement.get("customer_name") or ""),
            "law": str(procurement.get("procurement_law") or "44-ФЗ"),
            "source": str(procurement.get("procurement_source") or "public_eis_html_44fz"),
            "source_url": procurement_url,
        },
        "source_urls": source_urls,
        "acquired_at": acquired_at,
        "documents": documents,
        "source_scope": (
            "Original public 44-FZ procurement files acquired through the accepted "
            "read-only Tender Agent source path before any Tender Agent analysis output."
        ),
        "source_bundle_sha256": source_bundle_sha256(documents),
        "source_conflict": False,
        "provenance_sufficient": exact_attachment_provenance,
    }
    return manifest


def _attachment_source_map(procurement_details: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in procurement_details.get("attachments") or []:
        if not isinstance(item, dict):
            continue
        source_url = str(item.get("source_url") or "").strip()
        if not source_url:
            continue
        for key in ("stored_name", "name"):
            value = str(item.get(key) or "").strip()
            if value:
                mapping[value] = source_url
                mapping[Path(value).name] = source_url
    return mapping


def _write_evaluator_zip(case_dir: Path) -> Path:
    zip_path = case_dir.parent / f"{case_dir.name}-blind-evaluator-input.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for fixed in ("case_manifest.json", "evaluator_bundle.json"):
            archive.write(case_dir / fixed, arcname=fixed)
        for path in sorted((case_dir / "source").rglob("*")):
            if path.is_file():
                archive.write(path, arcname=path.relative_to(case_dir).as_posix())
    return zip_path


def prepare_phase_a(
    *,
    backend_url: str,
    registry_number: str,
    case_dir: Path,
    query: str,
    search_days: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    if case_dir.exists() and any(case_dir.iterdir()):
        raise E2EBlocked(
            "case_directory_not_empty",
            "Calibration case directory must be new or empty to prevent source/SUT mixing.",
            details={"case_dir": str(case_dir)},
        )
    case_dir.mkdir(parents=True, exist_ok=True)
    source_dir = case_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    credentials = _auth_credentials_from_env()
    client = BackendClient(
        backend_url,
        timeout_seconds=timeout_seconds,
        basic_auth=credentials,
    )
    today = date.today()
    search = client.search(
        query=query,
        law="44fz",
        max_results=50,
        date_from=(today - timedelta(days=search_days)).isoformat(),
        date_to=today.isoformat(),
    )
    cards = search.get("cards") or []
    if not isinstance(cards, list):
        raise E2EBlocked(
            "search_invalid_shape",
            "Public 44-FZ search returned a non-list cards field.",
            details={"outcome": search.get("outcome")},
        )
    card = select_exact_card(cards, registry_number)

    handoff = source_only_handoff(client, card=card, registry_number=registry_number)
    run_id = str(handoff.get("run_id") or "").strip()
    if not run_id:
        raise E2EBlocked("missing_run_id", "Source-only handoff did not return a run_id.")

    run_payload = client.get_run(run_id)
    assert_source_only_run(run_payload)
    procurement_details = client._json("GET", f"/api/demo/tender-agent/runs/{run_id}/procurement")
    source_map = _attachment_source_map(procurement_details)
    procurement_url = str(run_payload.get("procurement_url") or card.get("source_url") or "").strip()
    if not procurement_url:
        raise E2EBlocked(
            "missing_procurement_source_url",
            "Source-only calibration run cannot be tied to an exact public procurement URL.",
            details={"run_id": run_id, "registry_number": registry_number},
        )

    files = run_payload.get("files") or []
    if not files:
        raise E2EBlocked(
            "no_public_source_files",
            "The accepted public intake path returned no files for the calibration target.",
            details={"run_id": run_id, "status": run_payload.get("status")},
        )

    source_documents: list[dict[str, str]] = []
    used_names: set[str] = set()
    for index, item in enumerate(files, start=1):
        if not isinstance(item, dict):
            continue
        file_id = str(item.get("file_id") or "").strip()
        if not file_id:
            continue
        stored_name = str(item.get("stored_name") or "").strip()
        original_name = str(item.get("original_name") or stored_name).strip()
        safe_name = _safe_name(original_name, f"source-{index:03d}.bin")
        if safe_name in used_names:
            safe_name = f"{index:03d}-{safe_name}"
        used_names.add(safe_name)
        payload = _download_bytes(
            backend_url,
            f"/api/demo/tender-agent/runs/{run_id}/files/{file_id}/download",
            credentials=credentials,
            timeout_seconds=timeout_seconds,
        )
        output = source_dir / safe_name
        output.write_bytes(payload)
        source_url = (
            source_map.get(stored_name)
            or source_map.get(Path(stored_name).name)
            or source_map.get(original_name)
            or source_map.get(Path(original_name).name)
        )
        provenance_kind = "attachment_url" if source_url else "procurement_page_fallback"
        source_documents.append(
            {
                "path": output.relative_to(case_dir).as_posix(),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "source_url": source_url or procurement_url,
                "provenance_kind": provenance_kind,
            }
        )

    if not source_documents:
        raise E2EBlocked("no_downloadable_source_files", "No source bytes could be copied into the case bundle.")

    case_id = f"calibration-44fz-{registry_number}"
    manifest_procurement = dict(run_payload)
    manifest_procurement["procurement_url"] = procurement_url
    manifest = build_case_manifest(
        case_id=case_id,
        procurement=manifest_procurement,
        source_documents=source_documents,
        acquired_at=_now_iso(),
    )
    write_artifact(case_dir / "case_manifest.json", manifest, "case_manifest")
    verify_manifest_source_files(manifest, case_dir)

    evaluator_bundle = prepare_evaluator_bundle(manifest, prepared_at=_now_iso())
    write_artifact(case_dir / "evaluator_bundle.json", evaluator_bundle, "evaluator_bundle")
    evaluator_zip = _write_evaluator_zip(case_dir)

    result = {
        "status": "BENCHMARK_CALIBRATION_PHASE_A_READY",
        "case_id": case_id,
        "registry_number": registry_number,
        "run_id": run_id,
        "source_file_count": len(source_documents),
        "source_bundle_sha256": manifest["source_bundle_sha256"],
        "provenance_sufficient": manifest["provenance_sufficient"],
        "case_dir": str(case_dir),
        "evaluator_zip": str(evaluator_zip),
        "next_action": (
            "STOP. Provide the evaluator ZIP to the independent evaluator. "
            "Do not freeze labels or run Tender Agent analysis yet."
        ),
    }
    (case_dir / "phase-a-result.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-number", default=DEFAULT_REGISTRY_NUMBER)
    parser.add_argument("--query", default=None, help="Public search query; defaults to registry number.")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000")
    parser.add_argument("--case-dir", default=None)
    parser.add_argument("--search-days", type=int, default=120)
    parser.add_argument("--timeout-seconds", type=int, default=240)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    registry_number = str(args.registry_number).strip()
    case_dir = Path(
        args.case_dir
        or f"company_agent_runs/benchmark_calibration/calibration-44fz-{registry_number}"
    ).expanduser()
    try:
        result = prepare_phase_a(
            backend_url=args.backend_url,
            registry_number=registry_number,
            case_dir=case_dir,
            query=args.query or registry_number,
            search_days=max(1, int(args.search_days)),
            timeout_seconds=max(1, int(args.timeout_seconds)),
        )
    except E2EBlocked as exc:
        print(
            json.dumps(
                {
                    "status": "BENCHMARK_CALIBRATION_PHASE_A_BLOCKED",
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
