#!/usr/bin/env python3
"""One-command Mac mini procurement discovery -> analysis -> report proof.

This orchestrator deliberately composes the existing Tender Agent HTTP API rather
than duplicating procurement logic. It performs read-only public discovery,
selects the strongest deterministic relevance candidate that has not already
been selected by this local runner, hands the card to the existing intake path,
lets the backend obtain public documentation and run the controlled analysis,
then saves the generated HTML report locally.

It does NOT submit applications, send email, use a digital signature, log into an
ETP, bypass captcha, or mutate ARV-001 governance/evidence. Source or document
unavailability is a terminal, explicit result rather than a reason to fabricate a
report.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


READY_STATUSES = {"completed", "completed_with_warnings", "needs_review"}
_SELECTION_HISTORY_FILENAME = "selection-history.json"
_SELECTION_HISTORY_VERSION = 1
_AUTH_ENV_PAIRS = (
    ("AI_CORP_PILOT_AUTH_USERNAME", "AI_CORP_PILOT_AUTH_PASSWORD"),
    (
        "AI_CORP_TENDER_PILOT_BASIC_AUTH_USERNAME",
        "AI_CORP_TENDER_PILOT_BASIC_AUTH_PASSWORD",
    ),
)


class E2EBlocked(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class Selection:
    card: dict[str, Any]
    registry_number: str
    relevance_score: float


def _auth_credentials_from_env() -> tuple[str, str] | None:
    """Resolve local pilot Basic Auth without ever accepting a CLI password."""
    for username_key, password_key in _AUTH_ENV_PAIRS:
        username = os.environ.get(username_key)
        password = os.environ.get(password_key)
        if username is None and password is None:
            continue
        if not username or not password:
            raise E2EBlocked(
                "backend_auth_configuration_incomplete",
                "Tender pilot Basic Auth environment is incomplete.",
                details={
                    "username_env": username_key,
                    "password_env": password_key,
                    "username_present": bool(username),
                    "password_present": bool(password),
                },
            )
        if ":" in username:
            raise E2EBlocked(
                "backend_auth_configuration_invalid",
                "Tender pilot Basic Auth username must not contain ':'.",
                details={"username_env": username_key},
            )
        return username, password
    return None


def _basic_auth_header(credentials: tuple[str, str] | None) -> str | None:
    if credentials is None:
        return None
    username, password = credentials
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


class BackendClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: int = 240,
        basic_auth: tuple[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._authorization_header = _basic_auth_header(basic_auth)

    def _headers(self, accept: str, *, content_type: str | None = None) -> dict[str, str]:
        headers = {"Accept": accept}
        if content_type is not None:
            headers["Content-Type"] = content_type
        if self._authorization_header is not None:
            headers["Authorization"] = self._authorization_header
        return headers

    def _raise_http_error(self, exc: HTTPError, *, path: str, report: bool = False) -> None:
        payload_text = exc.read().decode("utf-8", errors="replace")
        if exc.code == 401:
            auth_configured = self._authorization_header is not None
            raise E2EBlocked(
                "backend_auth_rejected" if auth_configured else "backend_auth_required",
                (
                    "Tender Agent backend rejected the configured pilot authentication."
                    if auth_configured
                    else "Tender Agent backend requires pilot authentication."
                ),
                details={
                    "path": path,
                    "status": 401,
                    "auth_configured": auth_configured,
                    "body": payload_text[:2000],
                },
            ) from exc
        raise E2EBlocked(
            "report_http_error" if report else "backend_http_error",
            (
                f"Report endpoint returned HTTP {exc.code}"
                if report
                else f"Backend returned HTTP {exc.code} for {path}"
            ),
            details={"path": path, "status": exc.code, "body": payload_text[:2000]},
        ) from exc

    def _json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        form: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: bytes | None = None
        content_type: str | None = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            content_type = "application/json"
        elif form is not None:
            body = urlencode({key: value for key, value in form.items() if value is not None}).encode("utf-8")
            content_type = "application/x-www-form-urlencoded"
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=self._headers("application/json", content_type=content_type),
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - localhost/operator URL by design
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            self._raise_http_error(exc, path=path)
            raise AssertionError("unreachable")
        except URLError as exc:
            raise E2EBlocked(
                "backend_unavailable",
                f"Tender Agent backend is unavailable at {self.base_url}: {exc.reason}",
            ) from exc
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise E2EBlocked(
                "backend_invalid_json",
                f"Backend returned non-JSON response for {path}",
                details={"body": raw[:1000]},
            ) from exc
        if not isinstance(parsed, dict):
            raise E2EBlocked("backend_invalid_shape", f"Expected JSON object from {path}")
        return parsed

    def _text(self, path: str) -> str:
        request = Request(
            f"{self.base_url}{path}",
            headers=self._headers("text/html"),
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - localhost/operator URL by design
                return response.read().decode("utf-8")
        except HTTPError as exc:
            self._raise_http_error(exc, path=path, report=True)
            raise AssertionError("unreachable")
        except URLError as exc:
            raise E2EBlocked("backend_unavailable", f"Tender Agent backend is unavailable: {exc.reason}") from exc

    def search(
        self,
        *,
        query: str,
        law: str,
        max_results: int,
        date_from: str,
        date_to: str,
    ) -> dict[str, Any]:
        return self._json(
            "POST",
            "/api/demo/tender-agent/procurement/public-44fz-search",
            form={
                "query": query,
                "law": law,
                "max_results": max_results,
                "page_size": max_results,
                "date_from": date_from,
                "date_to": date_to,
            },
        )

    def handoff(self, selection: Selection, *, law: str) -> dict[str, Any]:
        card = selection.card
        return self._json(
            "POST",
            "/api/demo/tender-agent/runs/from-search-result",
            payload={
                "source": card.get("source") or "public_eis_html_44fz",
                "law": law,
                "reestr_number": selection.registry_number,
                "source_url": card.get("source_url"),
                "title": card.get("title"),
                "customer_name": card.get("customer_name"),
                "initial_price": card.get("initial_price"),
                "publication_date": card.get("publication_date"),
                "deadline": card.get("deadline"),
                "currency": card.get("currency") or "RUB",
                "status": card.get("status"),
                "procedure_type": card.get("procedure_type"),
                "download_archive": True,
                "analyze_after_download": True,
            },
        )

    def analyze(self, run_id: str) -> dict[str, Any]:
        return self._json("POST", f"/api/demo/tender-agent/runs/{run_id}/analyze", payload={})

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._json("GET", f"/api/demo/tender-agent/runs/{run_id}")

    def report_html(self, run_id: str) -> str:
        return self._text(f"/demo/tender-agent/runs/{run_id}/report")


def _registry_number(card: dict[str, Any]) -> str:
    for key in ("reestr_number", "registry_number", "notice_number", "procurement_number", "procurement_id"):
        value = str(card.get(key) or "").strip()
        if value:
            return value
    return ""


def _relevance_score(card: dict[str, Any]) -> float:
    relevance = card.get("relevance")
    if not isinstance(relevance, dict):
        return 0.0
    try:
        return float(relevance.get("score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_registry_numbers(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def _selection_history_path(output_dir: Path) -> Path:
    return output_dir / _SELECTION_HISTORY_FILENAME


def _load_selection_history(output_dir: Path) -> tuple[str, ...]:
    path = _selection_history_path(output_dir)
    if not path.exists():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise E2EBlocked(
            "selection_history_invalid",
            "Local procurement selection history cannot be read safely.",
            details={"path": str(path)},
        ) from exc
    if not isinstance(payload, dict) or payload.get("version") != _SELECTION_HISTORY_VERSION:
        raise E2EBlocked(
            "selection_history_invalid",
            "Local procurement selection history has an unsupported shape or version.",
            details={"path": str(path)},
        )
    registry_numbers = payload.get("registry_numbers")
    if not isinstance(registry_numbers, list) or not all(isinstance(item, str) for item in registry_numbers):
        raise E2EBlocked(
            "selection_history_invalid",
            "Local procurement selection history contains invalid registry numbers.",
            details={"path": str(path)},
        )
    return _normalize_registry_numbers(registry_numbers)


def _record_selection_history(output_dir: Path, registry_number: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = _load_selection_history(output_dir)
    registry_numbers = _normalize_registry_numbers((*existing, registry_number))
    path = _selection_history_path(output_dir)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "version": _SELECTION_HISTORY_VERSION,
        "registry_numbers": list(registry_numbers),
    }
    try:
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(path)
    except OSError as exc:
        raise E2EBlocked(
            "selection_history_write_failed",
            "Local procurement selection history could not be updated safely.",
            details={"path": str(path)},
        ) from exc
    return path


def choose_candidate(
    cards: list[dict[str, Any]],
    *,
    min_relevance: float,
    excluded_registry_numbers: Iterable[str] = (),
) -> Selection:
    excluded = set(_normalize_registry_numbers(excluded_registry_numbers))
    by_registry: dict[str, Selection] = {}
    discovered_registry_numbers: list[str] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        registry_number = _registry_number(card)
        if not registry_number:
            continue
        discovered_registry_numbers.append(registry_number)
        candidate = Selection(
            card=card,
            registry_number=registry_number,
            relevance_score=_relevance_score(card),
        )
        previous = by_registry.get(registry_number)
        if previous is None or (
            candidate.relevance_score,
            str(candidate.card.get("publication_date") or ""),
        ) > (
            previous.relevance_score,
            str(previous.card.get("publication_date") or ""),
        ):
            by_registry[registry_number] = candidate

    if not by_registry:
        raise E2EBlocked("no_usable_search_cards", "Search returned no cards with a registry number")

    candidates = [item for registry, item in by_registry.items() if registry not in excluded]
    if not candidates:
        raise E2EBlocked(
            "no_unique_search_cards",
            "Search returned only procurements that were already selected or explicitly excluded.",
            details={
                "excluded_registry_numbers": sorted(excluded),
                "discovered_registry_numbers": sorted(set(discovered_registry_numbers)),
            },
        )

    candidates.sort(
        key=lambda item: (
            item.relevance_score,
            str(item.card.get("publication_date") or ""),
            item.registry_number,
        ),
        reverse=True,
    )
    selected = candidates[0]
    if selected.relevance_score < min_relevance:
        raise E2EBlocked(
            "relevance_below_threshold",
            f"Best procurement relevance {selected.relevance_score:.1f} is below threshold {min_relevance:.1f}",
            details={
                "best_registry_number": selected.registry_number,
                "best_title": selected.card.get("title"),
                "best_relevance": selected.relevance_score,
                "excluded_registry_numbers": sorted(excluded),
            },
        )
    return selected


def _llm_summary(run_payload: dict[str, Any]) -> dict[str, Any]:
    events = run_payload.get("events") or []
    event_types = [str(item.get("event_type") or "") for item in events if isinstance(item, dict)]
    completed_event = next(
        (item for item in events if isinstance(item, dict) and item.get("event_type") == "llm_analysis_completed"),
        None,
    )
    fallback_event = next(
        (item for item in events if isinstance(item, dict) and item.get("event_type") == "stub_analysis_fallback"),
        None,
    )
    mode = str(run_payload.get("analysis_mode") or "unknown")
    return {
        "requested_by_backend": True,
        "invoked": bool(completed_event),
        "fallback_used": bool(fallback_event),
        "analysis_mode": mode,
        "evidence_event": completed_event or fallback_event,
        "event_types": [value for value in event_types if value in {"llm_analysis_completed", "stub_analysis_fallback"}],
    }


def _recent_publication_window(today: date | None = None) -> tuple[str, str]:
    end = today or datetime.now(UTC).date()
    return ((end - timedelta(days=3)).isoformat(), end.isoformat())


def execute(
    client: BackendClient,
    *,
    query: str,
    law: str,
    max_results: int,
    min_relevance: float,
    output_dir: Path,
    excluded_registry_numbers: Iterable[str] = (),
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    history_registry_numbers = _load_selection_history(output_dir)
    excluded = _normalize_registry_numbers((*history_registry_numbers, *excluded_registry_numbers))

    date_from, date_to = _recent_publication_window()
    search = client.search(
        query=query,
        law=law,
        max_results=max_results,
        date_from=date_from,
        date_to=date_to,
    )
    outcome = str(search.get("outcome") or "")
    cards = search.get("cards") or []
    if outcome != "success_with_results" or not isinstance(cards, list) or not cards:
        raise E2EBlocked(
            "search_not_actionable",
            str(search.get("message") or "Public procurement search produced no actionable result"),
            details={
                "outcome": outcome,
                "status": search.get("status"),
                "parser_status": search.get("parser_status"),
                "error": search.get("error"),
                "eis_search_url": search.get("eis_search_url"),
            },
        )

    selected = choose_candidate(
        cards,
        min_relevance=min_relevance,
        excluded_registry_numbers=excluded,
    )
    history_path = _record_selection_history(output_dir, selected.registry_number)

    handoff = client.handoff(selected, law=law)
    run_id = str(handoff.get("run_id") or "").strip()
    if not run_id:
        raise E2EBlocked("handoff_missing_run_id", "Procurement handoff did not return run_id")

    run_payload = client.get_run(run_id)
    status = str(run_payload.get("status") or handoff.get("status") or "")
    if status == "ready_to_analyze":
        client.analyze(run_id)
        run_payload = client.get_run(run_id)
        status = str(run_payload.get("status") or "")

    if status == "docs_required":
        raise E2EBlocked(
            "documents_required",
            "Selected procurement does not have a complete automatically retrievable document set",
            details={
                "run_id": run_id,
                "registry_number": selected.registry_number,
                "selection_history_path": str(history_path.resolve()),
                "attachments_status": run_payload.get("attachments_status"),
                "downloaded_files_count": run_payload.get("downloaded_files_count"),
                "warnings": run_payload.get("warnings") or handoff.get("warnings") or [],
            },
        )
    if status == "failed":
        raise E2EBlocked(
            "analysis_failed",
            "Tender analysis failed safely",
            details={
                "run_id": run_id,
                "registry_number": selected.registry_number,
                "selection_history_path": str(history_path.resolve()),
                "warnings": run_payload.get("warnings") or [],
            },
        )
    if status not in READY_STATUSES:
        raise E2EBlocked(
            "run_not_terminal",
            f"Run ended in unexpected status '{status or 'unknown'}'",
            details={
                "run_id": run_id,
                "registry_number": selected.registry_number,
                "selection_history_path": str(history_path.resolve()),
                "analysis_mode": run_payload.get("analysis_mode"),
            },
        )

    html = client.report_html(run_id)
    if "<html" not in html.lower() and "<!doctype html" not in html.lower():
        raise E2EBlocked("report_invalid_html", "Report endpoint did not return HTML", details={"run_id": run_id})
    report_path = output_dir / f"{run_id}-report.html"
    report_path.write_text(html, encoding="utf-8")

    relevance = selected.card.get("relevance") if isinstance(selected.card.get("relevance"), dict) else {}
    return {
        "status": "report_ready",
        "marker": "MACMINI_AUTONOMOUS_PROCUREMENT_E2E_REPORT_READY",
        "query": query,
        "law": law,
        "search": {
            "outcome": outcome,
            "source": search.get("source"),
            "returned_count": search.get("returned_count"),
            "eis_pages_fetched": search.get("eis_pages_fetched"),
            "publication_date_from": date_from,
            "publication_date_to": date_to,
        },
        "selection": {
            "method": "deterministic_highest_relevance_unique",
            "registry_number": selected.registry_number,
            "title": selected.card.get("title"),
            "customer_name": selected.card.get("customer_name"),
            "initial_price": selected.card.get("initial_price"),
            "deadline": selected.card.get("deadline"),
            "source_url": selected.card.get("source_url"),
            "relevance_score": selected.relevance_score,
            "relevance_status": relevance.get("status"),
            "relevance_reasons": relevance.get("reasons") or [],
            "excluded_registry_numbers": list(excluded),
            "selection_history_path": str(history_path.resolve()),
        },
        "run": {
            "run_id": run_id,
            "status": status,
            "attachments_status": run_payload.get("attachments_status"),
            "downloaded_files_count": run_payload.get("downloaded_files_count"),
            "analysis_mode": run_payload.get("analysis_mode"),
            "final_recommendation": run_payload.get("final_recommendation"),
        },
        "llm": _llm_summary(run_payload),
        "report": {
            "backend_url": f"{client.base_url}/demo/tender-agent/runs/{run_id}/report",
            "saved_path": str(report_path.resolve()),
        },
        "safety": {
            "read_only_discovery": True,
            "external_actions": False,
            "platform_submission": False,
            "email_sending": False,
            "digital_signature": False,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Mac mini procurement discovery -> analysis -> report E2E proof")
    parser.add_argument("--query", required=True, help="Procurement keyword query")
    parser.add_argument("--law", default="44fz", choices=["44fz"], help="First increment supports public 44-FZ search")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000")
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--min-relevance", type=float, default=20.0)
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument("--output-dir", type=Path, default=Path("company_agent_runs/macmini_autonomous_e2e"))
    parser.add_argument(
        "--exclude-registry-number",
        action="append",
        default=[],
        help="Registry number to exclude from deterministic selection; may be repeated.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        basic_auth = _auth_credentials_from_env()
        client = BackendClient(
            args.backend_url,
            timeout_seconds=args.timeout_seconds,
            basic_auth=basic_auth,
        )
        result = execute(
            client,
            query=args.query,
            law=args.law,
            max_results=max(1, min(args.max_results, 50)),
            min_relevance=max(0.0, min(args.min_relevance, 100.0)),
            output_dir=args.output_dir,
            excluded_registry_numbers=args.exclude_registry_number,
        )
    except E2EBlocked as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "marker": "MACMINI_AUTONOMOUS_PROCUREMENT_E2E_BLOCKED",
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 20
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
