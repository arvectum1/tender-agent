#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmarks.pipeline.comparator import aggregate_scorecard, compare_case
from benchmarks.pipeline.contracts import (
    SCHEMA_FILES,
    read_and_validate,
    validate_case_manifest_consistency,
    verify_manifest_source_files,
    write_json,
)
from benchmarks.pipeline.workflow import (
    freeze_labels,
    prepare_evaluator_bundle,
    promote_to_gold,
    route_failure,
    route_review,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cmd_validate(args: argparse.Namespace) -> None:
    payload = _load(args.input)
    if args.artifact_type == "case_manifest":
        validate_case_manifest_consistency(payload)
    else:
        read_and_validate(args.input, args.artifact_type)
    print(f"PASS {args.artifact_type}: {args.input}")


def cmd_prepare_blind(args: argparse.Namespace) -> None:
    manifest = _load(args.manifest)
    verify_manifest_source_files(manifest, args.source_root)
    bundle = prepare_evaluator_bundle(manifest, prepared_at=args.at or _now())
    write_json(args.output, bundle)
    print(f"WROTE blind evaluator bundle: {args.output}")


def cmd_freeze(args: argparse.Namespace) -> None:
    bundle = _load(args.bundle)
    discovery = _load(args.discovery)
    truth = _load(args.truth)
    receipt = freeze_labels(bundle, discovery, truth, frozen_at=args.at or _now())
    write_json(args.output, receipt)
    print(f"FROZEN label set: {args.output}")


def cmd_compare(args: argparse.Namespace) -> None:
    result = compare_case(
        _load(args.discovery),
        _load(args.truth),
        _load(args.bundle),
        _load(args.freeze),
        _load(args.sut_ref),
        _load(args.sut_output),
        compared_at=args.at or _now(),
    )
    write_json(args.output, result)
    print(f"WROTE comparison: {args.output}")


def cmd_route(args: argparse.Namespace) -> None:
    review = route_review(
        _load(args.comparison),
        _load(args.discovery),
        _load(args.truth),
        routed_at=args.at or _now(),
        confidence_threshold=args.confidence_threshold,
    )
    write_json(args.output, review)
    print(f"ROUTED {review['state']}: {args.output}")


def cmd_route_failure(args: argparse.Namespace) -> None:
    review = route_failure(
        args.case_id,
        routed_at=args.at or _now(),
        reason=args.reason,
    )
    write_json(args.output, review)
    print(f"ROUTED NEEDS_REVIEW: {args.output}")


def cmd_promote(args: argparse.Namespace) -> None:
    review = promote_to_gold(
        _load(args.review),
        promoted_by=args.by,
        promoted_at=args.at or _now(),
        approval_note=args.note,
    )
    write_json(args.output, review)
    print(f"PROMOTED HUMAN_VERIFIED_GOLD: {args.output}")


def cmd_scorecard(args: argparse.Namespace) -> None:
    comparisons = [_load(path) for path in args.comparison]
    reviews = [_load(path) for path in args.review]
    scorecard = aggregate_scorecard(
        comparisons,
        reviews,
        generated_at=args.at or _now(),
    )
    write_json(args.output, scorecard)
    print(f"WROTE scorecard: {args.output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="BENCHMARK-PIPELINE-001 deterministic contract/workflow CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("--type", dest="artifact_type", choices=sorted(SCHEMA_FILES), required=True)
    validate.add_argument("--input", required=True)
    validate.set_defaults(func=cmd_validate)

    blind = sub.add_parser("prepare-blind")
    blind.add_argument("--manifest", required=True)
    blind.add_argument("--source-root", required=True)
    blind.add_argument("--output", required=True)
    blind.add_argument("--at")
    blind.set_defaults(func=cmd_prepare_blind)

    freeze = sub.add_parser("freeze")
    freeze.add_argument("--bundle", required=True)
    freeze.add_argument("--discovery", required=True)
    freeze.add_argument("--truth", required=True)
    freeze.add_argument("--output", required=True)
    freeze.add_argument("--at")
    freeze.set_defaults(func=cmd_freeze)

    compare = sub.add_parser("compare")
    compare.add_argument("--bundle", required=True)
    compare.add_argument("--discovery", required=True)
    compare.add_argument("--truth", required=True)
    compare.add_argument("--freeze", required=True)
    compare.add_argument("--sut-ref", required=True)
    compare.add_argument("--sut-output", required=True)
    compare.add_argument("--output", required=True)
    compare.add_argument("--at")
    compare.set_defaults(func=cmd_compare)

    route = sub.add_parser("route-review")
    route.add_argument("--comparison", required=True)
    route.add_argument("--discovery", required=True)
    route.add_argument("--truth", required=True)
    route.add_argument("--output", required=True)
    route.add_argument("--confidence-threshold", type=float, default=0.80)
    route.add_argument("--at")
    route.set_defaults(func=cmd_route)

    failure = sub.add_parser("route-failure")
    failure.add_argument("--case-id", required=True)
    failure.add_argument("--reason", default="SCHEMA_OR_CONSISTENCY_FAILURE")
    failure.add_argument("--output", required=True)
    failure.add_argument("--at")
    failure.set_defaults(func=cmd_route_failure)

    promote = sub.add_parser("promote-gold")
    promote.add_argument("--review", required=True)
    promote.add_argument("--output", required=True)
    promote.add_argument("--by", required=True)
    promote.add_argument("--note", required=True)
    promote.add_argument("--at")
    promote.set_defaults(func=cmd_promote)

    scorecard = sub.add_parser("scorecard")
    scorecard.add_argument("--comparison", action="append", required=True)
    scorecard.add_argument("--review", action="append", required=True)
    scorecard.add_argument("--output", required=True)
    scorecard.add_argument("--at")
    scorecard.set_defaults(func=cmd_scorecard)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
