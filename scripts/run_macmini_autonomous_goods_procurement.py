#!/usr/bin/env python3
"""GOODS-scoped safety runner for fresh Mac mini procurement acceptance.

This wrapper composes ``run_macmini_autonomous_procurement`` without changing its
generic mixed-category behavior. It adds two pilot guardrails discovered by
PILOT-001-D04.3 runtime re-acceptance:

* obvious SERVICES/WORKS search cards are excluded before handoff;
* every terminal handoff is verified against the canonical machine-readable
  ``runtime_analysis.procurement_category`` and non-GOODS runs are reserved in
  selection history and skipped automatically;
* raw socket/stdlib timeouts are converted to structured ``E2EBlocked`` results
  instead of escaping the CLI as a traceback.

The wrapper performs no submission, email, signature, ETP login, captcha bypass,
or other external action.
"""

from __future__ import annotations

import json
import re
import socket
from pathlib import Path
from typing import Any, Iterable

from scripts import run_macmini_autonomous_procurement as base

_REQUIRED_CATEGORY = "GOODS"
_STRONG_NON_GOODS_PATTERNS = (
    r"^\s*оказани[ея]\s+услуг",
    r"^\s*выполнени[ея]\s+(?:ремонтных\s+)?работ",
    r"^\s*работы\s+по\b",
    r"^\s*услуги\s+по\b",
    r"^\s*ремонт\b",
    r"\bтехническ\w*\s+обслуживан",
    r"\bстроительн\w*\s+работ",
    r"\bремонтн\w*\s+работ",
    r"\bпроектн\w*\s+работ",
    r"\bпроектировани[ея]\b",
    r"\bреконструкци[яи]\b",
    r"\bпусконаладочн\w*\s+работ",
    r"\bмонтажн\w*\s+работ",
    r"\bдемонтажн\w*\s+работ",
    r"\bэксплуатаци[яи]\b",
)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _is_explicit_non_goods_title(title: Any) -> bool:
    text = _clean(title).lower()
    if not text:
        return False
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in _STRONG_NON_GOODS_PATTERNS)


def _runtime_category(run_payload: dict[str, Any]) -> str | None:
    runtime_analysis = run_payload.get("runtime_analysis")
    if not isinstance(runtime_analysis, dict):
        return None
    for key in ("procurement_category", "fallback_category"):
        value = _clean(runtime_analysis.get(key)).upper()
        if value:
            return value
    return None


def _prefilter_non_goods_registry_numbers(
    client: "SafeBackendClient",
    *,
    query: str,
    law: str,
    max_results: int,
) -> tuple[str, ...]:
    """Exclude only cards that are unambiguously non-GOODS from their title.

    This is deliberately conservative. Ambiguous cards are still allowed to the
    canonical handoff and are then checked against ``runtime_analysis``. That
    keeps search-card heuristics from becoming a substitute for document-bound
    runtime classification.
    """

    date_from, date_to = base._recent_publication_window()
    search = client.search(
        query=query,
        law=law,
        max_results=max_results,
        date_from=date_from,
        date_to=date_to,
    )
    if str(search.get("outcome") or "") != "success_with_results":
        return ()
    cards = search.get("cards")
    if not isinstance(cards, list):
        return ()

    excluded: list[str] = []
    for card in cards:
        if not isinstance(card, dict) or not _is_explicit_non_goods_title(card.get("title")):
            continue
        registry_number = base._registry_number(card)
        if registry_number:
            excluded.append(registry_number)
    return base._normalize_registry_numbers(excluded)


class SafeBackendClient(base.BackendClient):
    """Backend client that converts raw stdlib timeouts into fail-closed output."""

    def _json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        form: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return super()._json(method, path, payload=payload, form=form)
        except base.E2EBlocked:
            raise
        except (TimeoutError, socket.timeout) as exc:
            raise base.E2EBlocked(
                "backend_timeout",
                "Tender Agent backend request timed out safely.",
                details={
                    "path": path,
                    "timeout_seconds": self.timeout_seconds,
                    "base_url": self.base_url,
                },
            ) from exc

    def _text(self, path: str) -> str:
        try:
            return super()._text(path)
        except base.E2EBlocked:
            raise
        except (TimeoutError, socket.timeout) as exc:
            raise base.E2EBlocked(
                "backend_timeout",
                "Tender Agent report request timed out safely.",
                details={
                    "path": path,
                    "timeout_seconds": self.timeout_seconds,
                    "base_url": self.base_url,
                },
            ) from exc


def execute_goods(
    client: SafeBackendClient,
    *,
    query: str,
    law: str,
    max_results: int,
    min_relevance: float,
    output_dir: Path,
    excluded_registry_numbers: Iterable[str] = (),
    max_scope_candidates: int = 5,
) -> dict[str, Any]:
    """Return only a runtime-confirmed GOODS report-ready result.

    Non-GOODS terminal runs are not surfaced as success. They remain reserved in
    the shared local selection history and the next unique candidate is tried
    automatically. The exact runtime category, not the search query wording, is
    authoritative.
    """

    max_scope_candidates = max(1, min(int(max_scope_candidates), 20))
    prefiltered = _prefilter_non_goods_registry_numbers(
        client,
        query=query,
        law=law,
        max_results=max_results,
    )
    explicit_excluded = base._normalize_registry_numbers(
        (*excluded_registry_numbers, *prefiltered)
    )
    rejected_runtime: list[dict[str, Any]] = []

    for scope_attempt in range(1, max_scope_candidates + 1):
        try:
            result = base.execute(
                client,
                query=query,
                law=law,
                max_results=max_results,
                min_relevance=min_relevance,
                output_dir=output_dir,
                excluded_registry_numbers=explicit_excluded,
            )
        except base.E2EBlocked as exc:
            if exc.code == "no_unique_search_cards" and rejected_runtime:
                raise base.E2EBlocked(
                    "goods_scope_exhausted",
                    "No additional unique search cards remain after rejecting non-GOODS runtime results.",
                    details={
                        "required_category": _REQUIRED_CATEGORY,
                        "prefilter_excluded_registry_numbers": list(prefiltered),
                        "runtime_rejections": rejected_runtime,
                        "selection_error": exc.details,
                    },
                ) from exc
            raise

        run = result.get("run") if isinstance(result.get("run"), dict) else {}
        run_id = _clean(run.get("run_id"))
        if not run_id:
            raise base.E2EBlocked(
                "runtime_scope_missing_run_id",
                "Report-ready result did not expose a run_id for category verification.",
            )

        canonical_payload = client.get_run(run_id)
        actual_category = _runtime_category(canonical_payload)
        selection = result.get("selection") if isinstance(result.get("selection"), dict) else {}
        registry_number = _clean(selection.get("registry_number"))

        if actual_category == _REQUIRED_CATEGORY:
            selection["required_category"] = _REQUIRED_CATEGORY
            selection["category_scope_verified"] = True
            selection["prefilter_excluded_registry_numbers"] = list(prefiltered)
            run["runtime_analysis"] = canonical_payload.get("runtime_analysis")
            result["selection"] = selection
            result["run"] = run
            result["scope"] = {
                "policy": "runtime_goods_scope_v1",
                "required_category": _REQUIRED_CATEGORY,
                "verified_category": actual_category,
                "scope_attempt": scope_attempt,
                "max_scope_candidates": max_scope_candidates,
                "prefilter_excluded_registry_numbers": list(prefiltered),
                "runtime_rejections": rejected_runtime,
            }
            result["marker"] = "MACMINI_AUTONOMOUS_GOODS_PROCUREMENT_E2E_REPORT_READY"
            return result

        rejected_runtime.append(
            {
                "scope_attempt": scope_attempt,
                "registry_number": registry_number,
                "run_id": run_id,
                "actual_category": actual_category or "UNKNOWN",
                "reason": "runtime_category_mismatch",
            }
        )

    raise base.E2EBlocked(
        "goods_scope_exhausted",
        "Runtime-confirmed GOODS procurement was not found within the candidate limit.",
        details={
            "required_category": _REQUIRED_CATEGORY,
            "max_scope_candidates": max_scope_candidates,
            "prefilter_excluded_registry_numbers": list(prefiltered),
            "runtime_rejections": rejected_runtime,
        },
    )


def _parser():
    parser = base._parser()
    parser.description = "Run GOODS-scoped Mac mini procurement discovery -> analysis -> report E2E proof"
    parser.add_argument(
        "--max-scope-candidates",
        type=int,
        default=5,
        help="Maximum unique terminal candidates to inspect until runtime confirms GOODS.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        basic_auth = base._auth_credentials_from_env()
        client = SafeBackendClient(
            args.backend_url,
            timeout_seconds=args.timeout_seconds,
            basic_auth=basic_auth,
        )
        result = execute_goods(
            client,
            query=args.query,
            law=args.law,
            max_results=max(1, min(args.max_results, 50)),
            min_relevance=max(0.0, min(args.min_relevance, 100.0)),
            output_dir=args.output_dir,
            excluded_registry_numbers=args.exclude_registry_number,
            max_scope_candidates=args.max_scope_candidates,
        )
    except base.E2EBlocked as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "marker": "MACMINI_AUTONOMOUS_GOODS_PROCUREMENT_E2E_BLOCKED",
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
