from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Final, Sequence
import subprocess

from scripts.p8_05_temporal_acceptance_binding import canonical_sha256

ACK_SCHEMA_VERSION: Final = "arv001-external-source-outage-ack-v1"
AUTH_SCHEMA_VERSION: Final = "arv001-outage-quality-authorization-v1"
RESULT_SCHEMA_VERSION: Final = "arv001-outage-quality-result-v1"
ACK_DECISION: Final = "AUTHORIZE_QUALITY_ACCEPTANCE_ONLY"
AUTHORIZED_STATUS: Final = "AUTHORIZED_QUALITY_ONLY_UNDER_EXTERNAL_SOURCE_BLOCKER"
TEMPORAL_SOURCE_HEALTH: Final = "blocked_external_dependency"
BLOCKER_CODE: Final = "EIS_REPEATED_CODE_0_PROCESSING_ERROR"
APPROVAL_STATEMENT: Final = (
    "I authorize one ARV-001 quality-only acceptance run against the frozen real-EIS "
    "baseline while temporal EIS source health remains externally blocked."
)
_ACK_ID = re.compile(r"^[A-Za-z0-9._:-]{3,120}$")
_SUBJECT = re.compile(r"^[A-Za-z0-9._-]{2,64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_AUTOMATION_SUBJECTS = {
    "agent",
    "automation",
    "chatgpt",
    "codex",
    "opencode",
    "system",
}
_ACK_MAX_AGE = timedelta(hours=24)
_ACK_FUTURE_SKEW = timedelta(minutes=5)


class OutageQualityBindingBlocked(RuntimeError):
    def __init__(self, code: str, *, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}".rstrip())


def _parse_aware_datetime(value: object) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise OutageQualityBindingBlocked("BLOCKED_PRODUCT_OWNER_ACK_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OutageQualityBindingBlocked("BLOCKED_PRODUCT_OWNER_ACK_TIME_INVALID") from exc
    if parsed.tzinfo is None:
        raise OutageQualityBindingBlocked("BLOCKED_PRODUCT_OWNER_ACK_TIME_INVALID")
    return parsed.astimezone(UTC)


def load_ack(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise OutageQualityBindingBlocked("BLOCKED_PRODUCT_OWNER_ACK_MISSING")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise OutageQualityBindingBlocked("BLOCKED_PRODUCT_OWNER_ACK_INVALID") from exc
    if not isinstance(value, dict):
        raise OutageQualityBindingBlocked("BLOCKED_PRODUCT_OWNER_ACK_INVALID")
    return value


def validate_product_owner_ack(
    value: dict[str, Any],
    *,
    baseline: dict[str, Any],
    expected_head: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    required = {
        "schema_version",
        "task_id",
        "decision",
        "acknowledgement_id",
        "acknowledged_by",
        "actor_type",
        "acknowledged_at",
        "approval_statement",
        "expected_head",
        "baseline_id",
        "baseline_descriptor_sha256",
        "corpus_sha256",
        "policy_sha256",
        "external_blocker_code",
        "temporal_source_health",
        "generation_run_limit",
        "external_actions_authorized",
    }
    if set(value) != required:
        raise OutageQualityBindingBlocked("BLOCKED_PRODUCT_OWNER_ACK_SCHEMA_MISMATCH")

    head = str(expected_head or "").strip().lower()
    subject = str(value.get("acknowledged_by") or "").strip()
    ack_id = str(value.get("acknowledgement_id") or "").strip()
    baseline_digest = canonical_sha256(baseline)
    checks = (
        _GIT_SHA.fullmatch(head) is not None,
        value.get("schema_version") == ACK_SCHEMA_VERSION,
        value.get("task_id") == "ARV-001",
        value.get("decision") == ACK_DECISION,
        _ACK_ID.fullmatch(ack_id) is not None,
        _SUBJECT.fullmatch(subject) is not None,
        subject.lower() not in _FORBIDDEN_AUTOMATION_SUBJECTS,
        value.get("actor_type") == "human_product_owner",
        value.get("approval_statement") == APPROVAL_STATEMENT,
        value.get("expected_head") == head,
        value.get("baseline_id") == baseline.get("baseline_id"),
        value.get("baseline_descriptor_sha256") == baseline_digest,
        value.get("corpus_sha256") == baseline.get("corpus", {}).get("sha256"),
        value.get("policy_sha256") == baseline.get("policy", {}).get("sha256"),
        value.get("external_blocker_code") == BLOCKER_CODE,
        value.get("temporal_source_health") == TEMPORAL_SOURCE_HEALTH,
        value.get("generation_run_limit") == 1,
        value.get("external_actions_authorized") is False,
    )
    if not all(checks):
        raise OutageQualityBindingBlocked("BLOCKED_PRODUCT_OWNER_ACK_NOT_AUTHORIZABLE")

    observed_now = (now or datetime.now(UTC)).astimezone(UTC)
    acknowledged_at = _parse_aware_datetime(value.get("acknowledged_at"))
    if acknowledged_at > observed_now + _ACK_FUTURE_SKEW:
        raise OutageQualityBindingBlocked("BLOCKED_PRODUCT_OWNER_ACK_FROM_FUTURE")
    if observed_now - acknowledged_at > _ACK_MAX_AGE:
        raise OutageQualityBindingBlocked("BLOCKED_PRODUCT_OWNER_ACK_STALE")
    return dict(value)


def build_outage_authorization(
    *,
    baseline: dict[str, Any],
    ack: dict[str, Any],
    expected_head: str,
) -> dict[str, Any]:
    validate_product_owner_ack(
        ack,
        baseline=baseline,
        expected_head=expected_head,
    )
    ack_sha = canonical_sha256(ack)
    body: dict[str, Any] = {
        "schema_version": AUTH_SCHEMA_VERSION,
        "status": AUTHORIZED_STATUS,
        "authorization_scope": "one-local-complete-corpus-generation",
        "generation_run_limit": 1,
        "expected_head": expected_head,
        "baseline_id": baseline["baseline_id"],
        "baseline_descriptor_sha256": canonical_sha256(baseline),
        "registry_number": baseline["registry_number"],
        "corpus_sha256": baseline["corpus"]["sha256"],
        "policy_sha256": baseline["policy"]["sha256"],
        "product_owner_ack_sha256": ack_sha,
        "product_owner_ack_id": ack["acknowledgement_id"],
        "external_blocker_code": BLOCKER_CODE,
        "temporal_source_health": TEMPORAL_SOURCE_HEALTH,
        "p805_status": "BLOCKED_EXTERNAL_SOURCE",
        "provider_execution_authorized": True,
        "procurement_submission_authorized": False,
        "email_authorized": False,
        "digital_signature_authorized": False,
        "external_actions": False,
    }
    digest = canonical_sha256(body)
    return {
        **body,
        "manifest_sha256": digest,
        "manifest_integrity_ref": f"sha256:{digest}",
    }


def validate_outage_authorization(
    authorization: dict[str, Any],
    *,
    baseline: dict[str, Any],
    ack: dict[str, Any],
    expected_head: str,
) -> None:
    if not isinstance(authorization, dict):
        raise OutageQualityBindingBlocked("BLOCKED_OUTAGE_AUTHORIZATION_INVALID")
    body = {
        key: value
        for key, value in authorization.items()
        if key not in ("manifest_sha256", "manifest_integrity_ref")
    }
    checks = (
        authorization.get("schema_version") == AUTH_SCHEMA_VERSION,
        authorization.get("status") == AUTHORIZED_STATUS,
        authorization.get("generation_run_limit") == 1,
        authorization.get("expected_head") == expected_head,
        authorization.get("baseline_id") == baseline.get("baseline_id"),
        authorization.get("baseline_descriptor_sha256") == canonical_sha256(baseline),
        authorization.get("corpus_sha256") == baseline.get("corpus", {}).get("sha256"),
        authorization.get("policy_sha256") == baseline.get("policy", {}).get("sha256"),
        authorization.get("product_owner_ack_sha256") == canonical_sha256(ack),
        authorization.get("external_blocker_code") == BLOCKER_CODE,
        authorization.get("temporal_source_health") == TEMPORAL_SOURCE_HEALTH,
        authorization.get("p805_status") == "BLOCKED_EXTERNAL_SOURCE",
        authorization.get("provider_execution_authorized") is True,
        authorization.get("procurement_submission_authorized") is False,
        authorization.get("email_authorized") is False,
        authorization.get("digital_signature_authorized") is False,
        authorization.get("external_actions") is False,
        authorization.get("manifest_sha256") == canonical_sha256(body),
    )
    if not all(checks):
        raise OutageQualityBindingBlocked("BLOCKED_OUTAGE_AUTHORIZATION_INVALID")


def acknowledgement_consumption_marker(path: Path) -> Path:
    return path.with_name(path.name + ".consumed.json")


def consume_ack_once(path: Path, *, ack_sha256: str) -> Path:
    if not _SHA256.fullmatch(str(ack_sha256 or "")):
        raise OutageQualityBindingBlocked("BLOCKED_PRODUCT_OWNER_ACK_HASH_INVALID")
    marker = acknowledgement_consumption_marker(path)
    payload = {
        "schema_version": "arv001-external-source-outage-ack-consumption-v1",
        "ack_sha256": ack_sha256,
        "consumed_at": datetime.now(UTC).isoformat(),
        "generation_run_limit": 1,
    }
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise OutageQualityBindingBlocked("BLOCKED_PRODUCT_OWNER_ACK_ALREADY_CONSUMED") from exc
    try:
        os.write(fd, encoded)
    finally:
        os.close(fd)
    return marker


def execute_outage_authorized_once(
    authorization: dict[str, Any],
    command: Sequence[str],
    *,
    baseline: dict[str, Any],
    ack: dict[str, Any],
    expected_head: str,
    env: dict[str, str],
    cwd: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    validate_outage_authorization(
        authorization,
        baseline=baseline,
        ack=ack,
        expected_head=expected_head,
    )
    if not command:
        raise OutageQualityBindingBlocked("BLOCKED_ACCEPTANCE_COMMAND_MISSING")
    return runner(
        list(command),
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
