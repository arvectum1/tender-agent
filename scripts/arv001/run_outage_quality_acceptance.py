#!/usr/bin/env python3
"""Run one ARV-001 real quality acceptance while temporal EIS health is externally blocked.

This runner deliberately does not weaken or mark P8.05 as passed. It requires a
fresh, explicit human product-owner acknowledgement bound to the exact HEAD,
frozen real-EIS baseline, corpus hash and provider policy. The acknowledgement
is consumed once immediately before the only permitted provider-capable child
process is started.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.arv001.outage_quality_binding import (
    BLOCKER_CODE,
    RESULT_SCHEMA_VERSION,
    TEMPORAL_SOURCE_HEALTH,
    OutageQualityBindingBlocked,
    acknowledgement_consumption_marker,
    build_outage_authorization,
    consume_ack_once,
    execute_outage_authorized_once,
    load_ack,
    validate_product_owner_ack,
)
from scripts.p8_05_run_temporal_acceptance import _acceptance_command, _parse_success
from scripts.p8_05_temporal_acceptance_binding import (
    P805AcceptanceBindingBlocked,
    canonical_sha256,
    load_and_verify_frozen_baseline,
    load_frozen_candidate_material,
    safe_child_failure,
    write_manifest,
)

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_SUCCESS_MARKER = "ARV-001_QUALITY_ONLY_UNDER_EXTERNAL_SOURCE_BLOCKER_COMPLETE"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run exactly one ARV-001 complete-corpus quality acceptance against the "
            "frozen reproduced real-EIS baseline when live temporal EIS health is "
            "blocked by the separately recorded external dependency."
        )
    )
    parser.add_argument(
        "--baseline-descriptor",
        type=Path,
        default=PROJECT_ROOT / "config/arv001/acceptance_baseline.json",
    )
    parser.add_argument("--baseline-candidate-root", type=Path, required=True)
    parser.add_argument("--baseline-intake-root", type=Path)
    parser.add_argument("--database-path", type=Path, required=True)
    parser.add_argument("--initialize-database", action="store_true")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--approved-policy", type=Path, required=True)
    parser.add_argument("--acceptance-output-root", type=Path, required=True)
    parser.add_argument("--binding-root", type=Path, required=True)
    parser.add_argument("--product-owner-ack", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    return parser.parse_args()


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _outside_repository(path: Path, code: str) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    repo = PROJECT_ROOT.resolve(strict=True)
    if resolved == repo or repo in resolved.parents:
        raise OutageQualityBindingBlocked(code)
    return resolved


def _git_preflight(expected_head: str) -> None:
    try:
        actual_head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip()
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=PROJECT_ROOT, text=True
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=PROJECT_ROOT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise OutageQualityBindingBlocked("BLOCKED_GIT_PREFLIGHT_UNAVAILABLE") from exc
    if actual_head != expected_head:
        raise OutageQualityBindingBlocked("BLOCKED_REPOSITORY_HEAD_MISMATCH")
    if branch not in {"", "main"}:
        raise OutageQualityBindingBlocked("BLOCKED_REPOSITORY_NOT_MAIN_OR_DETACHED")
    if status:
        raise OutageQualityBindingBlocked("BLOCKED_REPOSITORY_WORKTREE_NOT_CLEAN")


def _preflight(args: argparse.Namespace) -> tuple[Path, Path, Path, Path, Path, Path, Path, Path, str]:
    head = str(args.expected_head or "").strip().lower()
    if not _HEX40.fullmatch(head):
        raise OutageQualityBindingBlocked("BLOCKED_EXPECTED_HEAD_INVALID")
    _git_preflight(head)
    try:
        candidate = args.baseline_candidate_root.expanduser().resolve(strict=True)
        intake = (args.baseline_intake_root or candidate).expanduser().resolve(strict=True)
        policy = args.approved_policy.expanduser().resolve(strict=True)
        descriptor = args.baseline_descriptor.expanduser().resolve(strict=True)
        ack_path = args.product_owner_ack.expanduser().resolve(strict=True)
    except OSError as exc:
        raise OutageQualityBindingBlocked("BLOCKED_REQUIRED_LOCAL_INPUT_MISSING") from exc
    if not candidate.is_dir() or not intake.is_dir():
        raise OutageQualityBindingBlocked("BLOCKED_FROZEN_BASELINE_ROOT_MISSING")
    if not policy.is_file() or policy.is_symlink():
        raise OutageQualityBindingBlocked("BLOCKED_APPROVED_POLICY_MISSING")
    if not descriptor.is_file() or descriptor.is_symlink():
        raise OutageQualityBindingBlocked("BLOCKED_FROZEN_BASELINE_MISSING")
    if not ack_path.is_file() or ack_path.is_symlink():
        raise OutageQualityBindingBlocked("BLOCKED_PRODUCT_OWNER_ACK_MISSING")

    binding = _outside_repository(args.binding_root, "BLOCKED_BINDING_ROOT_INSIDE_REPOSITORY")
    acceptance = _outside_repository(
        args.acceptance_output_root, "BLOCKED_ACCEPTANCE_OUTPUT_INSIDE_REPOSITORY"
    )
    database = _outside_repository(args.database_path, "BLOCKED_DATABASE_INSIDE_REPOSITORY")
    data_dir = _outside_repository(args.data_dir, "BLOCKED_DATA_DIR_INSIDE_REPOSITORY")
    _outside_repository(ack_path, "BLOCKED_PRODUCT_OWNER_ACK_INSIDE_REPOSITORY")
    if binding.exists():
        raise OutageQualityBindingBlocked("BLOCKED_BINDING_ROOT_ALREADY_EXISTS")
    if acceptance.exists():
        raise OutageQualityBindingBlocked("BLOCKED_ACCEPTANCE_OUTPUT_ALREADY_EXISTS")
    if acknowledgement_consumption_marker(ack_path).exists():
        raise OutageQualityBindingBlocked("BLOCKED_PRODUCT_OWNER_ACK_ALREADY_CONSUMED")
    return candidate, intake, binding, acceptance, database, data_dir, policy, ack_path, head


def _failure_result(
    *,
    code: str,
    acceptance_invocations: int,
    acknowledgement_consumed: bool,
    authorization: dict[str, Any] | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": "FAIL_CLOSED",
        "failure_code": code,
        "temporal_source_health": TEMPORAL_SOURCE_HEALTH,
        "external_blocker_code": BLOCKER_CODE,
        "p805_status": "BLOCKED_EXTERNAL_SOURCE",
        "authorization_status": (
            authorization.get("status") if isinstance(authorization, dict) else None
        ),
        "acknowledgement_consumed": acknowledgement_consumed,
        "acceptance_invocations": acceptance_invocations,
        "external_actions": False,
    }
    return {**body, "manifest_sha256": canonical_sha256(body)}


def main() -> int:
    binding: Path | None = None
    authorization: dict[str, Any] | None = None
    acceptance_invocations = 0
    acknowledgement_consumed = False
    try:
        args = _arguments()
        candidate, intake, binding, acceptance, database, data_dir, policy, ack_path, head = _preflight(args)
        baseline = load_and_verify_frozen_baseline(args.baseline_descriptor)
        if _sha256_file(policy) != baseline["policy"]["sha256"]:
            raise OutageQualityBindingBlocked("BLOCKED_APPROVED_POLICY_HASH_MISMATCH")
        baseline_snapshot = load_frozen_candidate_material(candidate, baseline)
        if (
            baseline_snapshot.get("physical_file_count") != baseline["corpus"]["physical_file_count"]
            or baseline_snapshot.get("logical_document_count") != baseline["corpus"]["logical_document_count"]
            or baseline_snapshot.get("corpus_sha256") != baseline["corpus"]["sha256"]
        ):
            raise OutageQualityBindingBlocked("BLOCKED_FROZEN_BASELINE_SNAPSHOT_MISMATCH")

        ack = load_ack(ack_path)
        validate_product_owner_ack(ack, baseline=baseline, expected_head=head)
        ack_sha = canonical_sha256(ack)
        authorization = build_outage_authorization(
            baseline=baseline,
            ack=ack,
            expected_head=head,
        )

        binding.mkdir(parents=True, mode=0o700)
        write_manifest(binding / "product-owner-ack.snapshot.json", ack)
        write_manifest(binding / "outage-quality-authorization.json", authorization)

        command = _acceptance_command(
            candidate_root=candidate,
            intake_root=intake,
            database_path=database,
            data_dir=data_dir,
            approved_policy=policy,
            output_root=acceptance,
            expected_head=head,
            registry_number=baseline["registry_number"],
            corpus_sha256=baseline["corpus"]["sha256"],
            policy_sha256=baseline["policy"]["sha256"],
            initialize_database=args.initialize_database,
        )

        # Re-read immediately before the irreversible one-shot boundary. Any
        # acknowledgement mutation after authorization construction fails closed.
        if canonical_sha256(load_ack(ack_path)) != ack_sha:
            raise OutageQualityBindingBlocked("BLOCKED_PRODUCT_OWNER_ACK_CHANGED")
        consume_ack_once(ack_path, ack_sha256=ack_sha)
        acknowledgement_consumed = True
        acceptance_invocations = 1
        completed = execute_outage_authorized_once(
            authorization,
            command,
            baseline=baseline,
            ack=ack,
            expected_head=head,
            env=os.environ.copy(),
            cwd=PROJECT_ROOT,
        )
        if completed.returncode != 0:
            failure = _failure_result(
                code=safe_child_failure(completed.stderr),
                acceptance_invocations=1,
                acknowledgement_consumed=True,
                authorization=authorization,
            )
            write_manifest(binding / "outage-quality-result.json", failure)
            _print(failure)
            return 3

        success = _parse_success(
            completed.stdout,
            expected_head=head,
            expected_corpus=baseline["corpus"]["sha256"],
        )
        body = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "status": "QUALITY_ACCEPTANCE_COMPLETE_UNDER_EXTERNAL_SOURCE_BLOCKER",
            "marker": _SUCCESS_MARKER,
            "temporal_source_health": TEMPORAL_SOURCE_HEALTH,
            "external_blocker_code": BLOCKER_CODE,
            "p805_status": "BLOCKED_EXTERNAL_SOURCE",
            "quality_evidence_class": "real_frozen_reproduced_eis",
            "expected_head": head,
            "baseline_id": baseline["baseline_id"],
            "baseline_descriptor_sha256": canonical_sha256(baseline),
            "corpus_sha256": baseline["corpus"]["sha256"],
            "policy_sha256": baseline["policy"]["sha256"],
            "product_owner_ack_sha256": ack_sha,
            "authorization_manifest_sha256": authorization["manifest_sha256"],
            "acknowledgement_consumed": True,
            "acceptance_invocations": 1,
            "controlled_invocation_count": success["controlled_invocation_count"],
            "execution_count": success.get("execution_count"),
            "repeat_identity_verified": success.get("repeat_identity_verified"),
            "artifact_hashes": success["artifact_hashes"],
            "production_db_mutations": 0,
            "old_arv003_mutations": 0,
            "git_mutations": 0,
            "external_actions": False,
        }
        final = {**body, "manifest_sha256": canonical_sha256(body)}
        write_manifest(binding / "outage-quality-result.json", final)
        _print(final)
        return 0
    except (OutageQualityBindingBlocked, P805AcceptanceBindingBlocked) as exc:
        code = getattr(exc, "code", "BLOCKED_OUTAGE_QUALITY_ACCEPTANCE")
        failure = _failure_result(
            code=code,
            acceptance_invocations=acceptance_invocations,
            acknowledgement_consumed=acknowledgement_consumed,
            authorization=authorization,
        )
        if binding is not None and binding.is_dir():
            write_manifest(binding / "outage-quality-result.json", failure)
        _print(failure)
        return 2
    except Exception as exc:  # noqa: BLE001 - sanitize terminal boundary.
        failure = _failure_result(
            code=f"runtime_error:{type(exc).__name__}",
            acceptance_invocations=acceptance_invocations,
            acknowledgement_consumed=acknowledgement_consumed,
            authorization=authorization,
        )
        if binding is not None and binding.is_dir():
            write_manifest(binding / "outage-quality-result.json", failure)
        _print(failure)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
