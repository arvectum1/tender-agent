#!/usr/bin/env python3
"""One-command local runner for the ARV-001 decision-useful PO candidate.

The command discovers the already-existing frozen candidate/intake pair under
bounded private scopes, proves all frozen source bytes through canonical
preparation, binds to the accepted canonical report, and delegates to the
fail-closed zero-provider candidate builder. It then verifies that the material
terms which passed extraction are still visible in final customer HTML.

The accepted canonical path is also used as a locality hint: the containing
``arv001-*`` runtime root is searched before broad private storage. This changes
only discovery order; exact corpus/source/document/render verification remains
mandatory.

It performs no provider, EIS, RAG, acknowledgement, acceptance, production DB,
or Git mutation.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from scripts.arv001.build_decision_useful_candidate import (
    DEFAULT_ACCEPTED_CANONICAL_SHA256,
    build_candidate,
)
from scripts.arv001.complete_corpus_contract import (
    DEFAULT_CORPUS_SHA256,
    DEFAULT_REGISTRY_NUMBER,
    AcceptanceBlocked,
)
from scripts.arv001.discover_decision_useful_inputs import discover_inputs
from scripts.arv001.validate_decision_useful_candidate import (
    validate_rendered_material_terms,
)

DEFAULT_CANONICAL_OUTPUT = Path(
    "/private/tmp/arv001-final-runtime-20260827065002/acceptance/"
    "controlled-evidence/execution-1/canonical_report.json"
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover frozen ARV-001 inputs and build one local PO candidate."
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--canonical-output", type=Path, default=DEFAULT_CANONICAL_OUTPUT
    )
    parser.add_argument(
        "--search-root",
        type=Path,
        action="append",
        dest="search_roots",
        help="Private discovery root; may be repeated.",
    )
    parser.add_argument(
        "--expected-registry-number", default=DEFAULT_REGISTRY_NUMBER
    )
    parser.add_argument("--expected-corpus-sha", default=DEFAULT_CORPUS_SHA256)
    parser.add_argument(
        "--expected-canonical-sha", default=DEFAULT_ACCEPTED_CANONICAL_SHA256
    )
    return parser.parse_args()


def _failure(code: str) -> int:
    if not code.isascii() or len(code) > 300:
        code = "decision_useful_local_runner_failed"
    print(
        json.dumps(
            {
                "status": "FAIL_CLOSED",
                "failure_code": code,
                "provider_calls_performed": False,
                "eis_requests_performed": False,
                "rag_rerun": False,
                "quality_acceptance_rerun": False,
                "acknowledgement_touched": False,
                "production_db_mutations": 0,
                "git_mutations": 0,
                "product_owner": "REJECTED",
                "independent_review": "NOT_AUTHORIZED",
                "freeze": "NOT_ALLOWED",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 2


def _canonical_runtime_root(canonical: Path) -> Path:
    """Return the narrowest stable ARV-001 runtime ancestor for discovery."""

    resolved = canonical.expanduser().resolve(strict=False)
    for parent in resolved.parents:
        if parent.name.startswith("arv001-"):
            return parent
    return resolved.parent


def _default_search_roots(canonical: Path) -> list[Path]:
    """Prioritize bounded accepted-runtime locality before broad fallbacks."""

    candidates = [
        _canonical_runtime_root(canonical),
        Path.home() / ".local/share/arvectum/arv001",
        Path("/private/tmp"),
    ]
    result: list[Path] = []
    seen: set[Path] = set()
    for value in candidates:
        resolved = value.expanduser().resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


def _validate_published_candidate(output_root: Path) -> dict:
    html_path = output_root / "upload-ready-report-decision-useful.html"
    analysis_path = output_root / "decision-useful-analysis.json"
    if not html_path.is_file() or html_path.is_symlink():
        raise AcceptanceBlocked("decision_useful_rendered_html_missing")
    if not analysis_path.is_file() or analysis_path.is_symlink():
        raise AcceptanceBlocked("decision_useful_rendered_analysis_missing")
    try:
        rendered = html_path.read_text(encoding="utf-8")
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcceptanceBlocked("decision_useful_rendered_candidate_unreadable") from exc
    if not isinstance(analysis, dict):
        raise AcceptanceBlocked("decision_useful_rendered_analysis_invalid")
    return validate_rendered_material_terms(rendered, analysis)


def main() -> int:
    args = _arguments()
    try:
        canonical = args.canonical_output.expanduser().resolve(strict=True)
        search_roots = args.search_roots or _default_search_roots(canonical)
        discovery = discover_inputs(
            search_roots=search_roots,
            expected_corpus_sha=args.expected_corpus_sha,
        )
        result = build_candidate(
            canonical_output=canonical,
            candidate_root=Path(discovery["candidate_root"]),
            intake_root=Path(discovery["intake_root"]),
            output_root=args.output_root,
            expected_registry_number=args.expected_registry_number,
            expected_corpus_sha=args.expected_corpus_sha,
            expected_canonical_sha=args.expected_canonical_sha,
        )
    except AcceptanceBlocked as exc:
        return _failure(str(exc))
    except OSError:
        return _failure("decision_useful_required_local_input_missing")

    output_root = args.output_root.expanduser().resolve(strict=False)
    try:
        rendered_validation = _validate_published_candidate(output_root)
    except AcceptanceBlocked as exc:
        # A builder result that loses material detail during rendering is not a
        # candidate. Remove only the just-created output root; frozen evidence
        # and accepted canonical inputs remain read-only.
        shutil.rmtree(output_root, ignore_errors=True)
        return _failure(str(exc))

    print(
        json.dumps(
            {
                "status": result["status"],
                "marker": "ARV001_DECISION_USEFUL_LOCAL_CANDIDATE_READY",
                "report_sha256": result["report_sha256"],
                "material_detail_count": result["material_detail_count"],
                "decision_usefulness_gate": result["decision_usefulness_gate"][
                    "status"
                ],
                "decision_usefulness_checks": result["decision_usefulness_gate"][
                    "checks"
                ],
                "rendered_material_validation": rendered_validation,
                "canonical_sha256": result["accepted_canonical_sha256"],
                "frozen_corpus_sha256": result["frozen_corpus_sha256"],
                "physical_document_count": result["physical_document_count"],
                "logical_document_count": result["logical_document_count"],
                "source_bytes_verified": bool(discovery.get("source_bytes_verified")),
                "verified_private_input_pairs": int(
                    discovery.get("verified_pair_count") or 1
                ),
                "selected_discovery_scope": discovery.get(
                    "selected_discovery_scope"
                ),
                "oversized_scopes_skipped_before_match": int(
                    discovery.get("oversized_scopes_skipped_before_match") or 0
                ),
                "output_root": str(output_root),
                "provider_calls_performed": False,
                "eis_requests_performed": False,
                "rag_rerun": False,
                "quality_acceptance_rerun": False,
                "acknowledgement_touched": False,
                "accepted_canonical_mutated": False,
                "frozen_source_bytes_mutated": False,
                "production_db_mutations": 0,
                "git_mutations": 0,
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
