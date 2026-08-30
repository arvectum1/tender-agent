#!/usr/bin/env python3
"""One-command Mac mini procurement discovery -> analysis -> report proof.

This orchestrator deliberately composes the existing Tender Agent HTTP API rather
than duplicating procurement logic.  It performs read-only public discovery,
selects the strongest deterministic relevance candidate, hands the card to the
existing intake path, lets the backend obtain public documentation and run the
controlled analysis, then saves the generated HTML report locally.

It does NOT submit applications, send email, use a digital signature, log into an
ETP, bypass captcha, or mutate ARV-001 governance/evidence.  Source or document
unavailability is a terminal, explicit result rather than a reason to fabricate a
report.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


READY_STATUSES = {"completed", "completed_with_warnings", "needs_review"}


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


class BackendClient:
    def __init__(self, base_url: str, *, timeout_seconds: int = 240) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        form: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: bytes | None = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif form is not None:
            body = urlencode({key: value for key, value in form.items() if value is not None}).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - localhost/operator URL by design
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            payload_text = exc.read().decode("utf-8", errors="replace")
            raise E2EBlocked(
                "backend_http_error",
                f"Backend returned HTTP {exc.code} for {path}",
                details={"path": path, "status": exc.code, "body": payload_text[:2000]},
            ) from exc
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
        request = Request(f"{self.base_url}{path}", headers={"Accept": "text/html"}, method="GET")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - localhost/operator URL by design
                return response.read().decode("utf-8")
        except HTTPError as exc:
            payload_text = exc.read().decode("utf-8", errors="replace")
            raise E2EBlocked(
                "report_http_error",
                f"Report endpoint returned HTTP {exc.code}",
                details={"path": path, "status": exc.code, "body": payload_text[:2000]},
            ) from exc
        except URLError as exc:
            raise E2EBlocked("backend_unavailable", f"Tender Agent backend is unavailable: {exc.reason}") from exc

    def search(self, *, query: str, law: str, max_results: int) -> dict[str, Any]:
        return self._json(
            "POST",
            "/api/demo/tender-agent/procurement/public-44fz-search",
            form={"query": query, "law": law, "max_results": max_results, "page_size": max_results},
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


def choose_candidate(cards: list[dict[str, Any]], *, min_relevance: float) -> Selection:
    candidates: list[Selection] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        registry_number = _registry_number(card)
        if not registry_number:
            continue
        candidates.append(
            Selection(
                card=card,
                registry_number=registry_number,
                relevance_score=_relevance_score(card),
            )
        )
    if not candidates:
        raise E2EBlocked("no_usable_search_cards", "Search returned no cards with a registry number")
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


def execute(
    client: BackendClient,
    *,
    query: str,
    law: str,
    max_results: int,
    min_relevance: float,
    output_dir: Path,
) -> dict[str, Any]:
    search = client.search(query=query, law=law, max_results=max_results)
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

    selected = choose_candidate(cards, min_relevance=min_relevance)
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
                "attachments_status": run_payload.get("attachments_status"),
                "downloaded_files_count": run_payload.get("downloaded_files_count"),
                "warnings": run_payload.get("warnings") or handoff.get("warnings") or [],
            },
        )
    if status == "failed":
        raise E2EBlocked(
            "analysis_failed",
            "Tender analysis failed safely",
            details={"run_id": run_id, "warnings": run_payload.get("warnings") or []},
        )
    if status not in READY_STATUSES:
        raise E2EBlocked(
            "run_not_terminal",
            f"Run ended in unexpected status '{status or 'unknown'}'",
            details={"run_id": run_id, "analysis_mode": run_payload.get("analysis_mode")},
        )

    html = client.report_html(run_id)
    if "<html" not in html.lower() and "<!doctype html" not in html.lower():
        raise E2EBlocked("report_invalid_html", "Report endpoint did not return HTML", details={"run_id": run_id})
    output_dir.mkdir(parents=True, exist_ok=True)
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
        },
        "selection": {
            "method": "deterministic_highest_relevance",
            "registry_number": selected.registry_number,
            "title": selected.card.get("title"),
            "customer_name": selected.card.get("customer_name"),
            "initial_price": selected.card.get("initial_price"),
            "deadline": selected.card.get("deadline"),
            "source_url": selected.card.get("source_url"),
            "relevance_score": selected.relevance_score,
            "relevance_status": relevance.get("status"),
            "relevance_reasons": relevance.get("reasons") or [],
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    client = BackendClient(args.backend_url, timeout_seconds=args.timeout_seconds)
    try:
        result = execute(
            client,
            query=args.query,
            law=args.law,
            max_results=max(1, min(args.max_results, 50)),
            min_relevance=max(0.0, min(args.min_relevance, 100.0)),
            output_dir=args.output_dir,
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
