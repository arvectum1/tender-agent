#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.modules.benchmark_pipeline import (
    aggregate_scorecard,
    compare_case,
    freeze_blind_labels,
    load_artifact,
    prepare_evaluator_bundle,
    promote_to_gold,
    route_review,
    validate_artifact,
    validate_case_manifest_consistency,
    verify_manifest_source_files,
    write_artifact,
)


ARTIFACT_KINDS = (
    "case_manifest",
    "evaluator_bundle",
    "blind_discovery_label",
    "blind_document_truth",
    "frozen_label",
    "tender_agent_output_ref",
    "normalized_sut_output",
    "comparison_result",
    "review_state",
    "aggregate_scorecard",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cmd_validate(args: argparse.Namespace) -> None:
    value = _read(args.input)
    if args.kind == "case_manifest":
        validate_case_manifest_consistency(value)
    else:
        validate_artifact(args.kind, value)
    print(f"PASS {args.kind}: {args.input}")


def cmd_prepare_blind(args: argparse.Namespace) -> None:
    manifest = _read(args.manifest)
    verify_manifest_source_files(manifest, args.source_root)
    bundle = prepare_evaluator_bundle(manifest, prepared_at=args.at or _now())
    write_artifact(args.output, bundle, "evaluator_bundle")
    print(f"WROTE evaluator_bundle: {args.output}")


def cmd_freeze(args: argparse.Namespace) -> None:
    bundle = load_artifact(args.bundle, "evaluator_bundle")
    discovery = load_artifact(args.discovery, "blind_discovery_label")
    truth = load_artifact(args.truth, "blind_document_truth")
    receipt = freeze_blind_labels(
        bundle,
        discovery,
        truth,
        frozen_at=args.at or _now(),
    )
    write_artifact(args.output, receipt, "frozen_label")
    print(f"FROZEN label set: {args.output}")


def cmd_compare(args: argparse.Namespace) -> None:
    result = compare_case(
        discovery_label=load_artifact(args.discovery, "blind_discovery_label"),
        document_truth=load_artifact(args.truth, "blind_document_truth"),
        evaluator_bundle=load_artifact(args.bundle, "evaluator_bundle"),
        freeze_receipt=load_artifact(args.freeze, "frozen_label"),
        sut_ref=load_artifact(args.sut_ref, "tender_agent_output_ref"),
        sut_output=load_artifact(args.sut_output, "normalized_sut_output"),
        compared_at=args.at or _now(),
    )
    write_artifact(args.output, result, "comparison_result")
    print(f"WROTE comparison_result: {args.output}")


def cmd_route(args: argparse.Namespace) -> None:
    review = route_review(
        load_artifact(args.manifest, "case_manifest"),
        load_artifact(args.discovery, "blind_discovery_label"),
        load_artifact(args.truth, "blind_document_truth"),
        load_artifact(args.freeze, "frozen_label"),
        load_artifact(args.comparison, "comparison_result"),
        confidence_threshold=args.confidence_threshold,
        updated_at=args.at or _now(),
    )
    write_artifact(args.output, review, "review_state")
    print(f"ROUTED {review['state']}: {args.output}")


def cmd_promote(args: argparse.Namespace) -> None:
    review = promote_to_gold(
        load_artifact(args.review, "review_state"),
        reviewer_id=args.reviewer,
        approval_note=args.note,
        updated_at=args.at or _now(),
    )
    write_artifact(args.output, review, "review_state")
    print(f"PROMOTED HUMAN_VERIFIED_GOLD: {args.output}")


def cmd_scorecard(args: argparse.Namespace) -> None:
    comparisons = [load_artifact(path, "comparison_result") for path in args.comparison]
    reviews = [load_artifact(path, "review_state") for path in args.review]
    scorecard = aggregate_scorecard(
        comparisons,
        reviews,
        generated_at=args.at or _now(),
    )
    write_artifact(args.output, scorecard, "aggregate_scorecard")
    print(f"WROTE aggregate_scorecard: {args.output}")


def _case_paths(case_dir: Path) -> dict[str, Path]:
    return {
        "manifest": case_dir / "case_manifest.json",
        "bundle": case_dir / "evaluator_bundle.json",
        "discovery": case_dir / "blind_discovery_label.json",
        "truth": case_dir / "blind_document_truth.json",
        "freeze": case_dir / "frozen_label.json",
        "sut_ref": case_dir / "tender_agent_output_ref.json",
        "sut_output": case_dir / "normalized_sut_output.json",
        "comparison": case_dir / "comparison_result.json",
        "review": case_dir / "review_state.json",
    }


def cmd_batch_compare(args: argparse.Namespace) -> None:
    root = Path(args.root)
    comparisons: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    case_dirs = sorted(path.parent for path in root.glob("*/case_manifest.json"))
    if not case_dirs:
        raise SystemExit(f"no case directories found under {root}")

    for case_dir in case_dirs:
        paths = _case_paths(case_dir)
        result = compare_case(
            discovery_label=load_artifact(paths["discovery"], "blind_discovery_label"),
            document_truth=load_artifact(paths["truth"], "blind_document_truth"),
            evaluator_bundle=load_artifact(paths["bundle"], "evaluator_bundle"),
            freeze_receipt=load_artifact(paths["freeze"], "frozen_label"),
            sut_ref=load_artifact(paths["sut_ref"], "tender_agent_output_ref"),
            sut_output=load_artifact(paths["sut_output"], "normalized_sut_output"),
            compared_at=args.at or _now(),
        )
        review = route_review(
            load_artifact(paths["manifest"], "case_manifest"),
            load_artifact(paths["discovery"], "blind_discovery_label"),
            load_artifact(paths["truth"], "blind_document_truth"),
            load_artifact(paths["freeze"], "frozen_label"),
            result,
            confidence_threshold=args.confidence_threshold,
            updated_at=args.at or _now(),
        )
        write_artifact(paths["comparison"], result, "comparison_result")
        write_artifact(paths["review"], review, "review_state")
        comparisons.append(result)
        reviews.append(review)
        print(f"{case_dir.name}: {review['state']}")

    scorecard = aggregate_scorecard(
        comparisons,
        reviews,
        generated_at=args.at or _now(),
    )
    output = root / "aggregate_scorecard.json"
    write_artifact(output, scorecard, "aggregate_scorecard")
    print(f"WROTE aggregate_scorecard: {output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="BENCHMARK-PIPELINE-001 deterministic blind-evaluation CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("--kind", choices=ARTIFACT_KINDS, required=True)
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
    route.add_argument("--manifest", required=True)
    route.add_argument("--discovery", required=True)
    route.add_argument("--truth", required=True)
    route.add_argument("--freeze", required=True)
    route.add_argument("--comparison", required=True)
    route.add_argument("--output", required=True)
    route.add_argument("--confidence-threshold", type=float, default=0.80)
    route.add_argument("--at")
    route.set_defaults(func=cmd_route)

    promote = sub.add_parser("promote-gold")
    promote.add_argument("--review", required=True)
    promote.add_argument("--reviewer", required=True)
    promote.add_argument("--note", required=True)
    promote.add_argument("--output", required=True)
    promote.add_argument("--at")
    promote.set_defaults(func=cmd_promote)

    scorecard = sub.add_parser("scorecard")
    scorecard.add_argument("--comparison", action="append", required=True)
    scorecard.add_argument("--review", action="append", required=True)
    scorecard.add_argument("--output", required=True)
    scorecard.add_argument("--at")
    scorecard.set_defaults(func=cmd_scorecard)

    batch = sub.add_parser("batch-compare")
    batch.add_argument("--root", required=True)
    batch.add_argument("--confidence-threshold", type=float, default=0.80)
    batch.add_argument("--at")
    batch.set_defaults(func=cmd_batch_compare)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
