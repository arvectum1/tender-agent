from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.arv001.outage_quality_binding import (
    ACK_DECISION,
    ACK_SCHEMA_VERSION,
    APPROVAL_STATEMENT,
    AUTHORIZED_STATUS,
    BLOCKER_CODE,
    TEMPORAL_SOURCE_HEALTH,
    OutageQualityBindingBlocked,
    acknowledgement_consumption_marker,
    build_outage_authorization,
    canonical_sha256,
    consume_ack_once,
    execute_outage_authorized_once,
    validate_outage_authorization,
    validate_product_owner_ack,
)
from scripts.p8_05_temporal_acceptance_binding import load_and_verify_frozen_baseline

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "config/arv001/acceptance_baseline.json"
HEAD = "5c012e1b9c43d0e5e536b8823993cffea87e1199"


def _baseline() -> dict:
    return load_and_verify_frozen_baseline(BASELINE_PATH)


def _ack(*, when: datetime | None = None, head: str = HEAD, subject: str = "product.owner") -> dict:
    baseline = _baseline()
    return {
        "schema_version": ACK_SCHEMA_VERSION,
        "task_id": "ARV-001",
        "decision": ACK_DECISION,
        "acknowledgement_id": "arv001-outage-ack-001",
        "acknowledged_by": subject,
        "actor_type": "human_product_owner",
        "acknowledged_at": (when or datetime.now(UTC)).isoformat(),
        "approval_statement": APPROVAL_STATEMENT,
        "expected_head": head,
        "baseline_id": baseline["baseline_id"],
        "baseline_descriptor_sha256": canonical_sha256(baseline),
        "corpus_sha256": baseline["corpus"]["sha256"],
        "policy_sha256": baseline["policy"]["sha256"],
        "external_blocker_code": BLOCKER_CODE,
        "temporal_source_health": TEMPORAL_SOURCE_HEALTH,
        "generation_run_limit": 1,
        "external_actions_authorized": False,
    }


def test_valid_human_product_owner_ack_authorizes_exact_bound_run() -> None:
    baseline = _baseline()
    ack = _ack()
    validated = validate_product_owner_ack(ack, baseline=baseline, expected_head=HEAD)
    authorization = build_outage_authorization(
        baseline=baseline,
        ack=validated,
        expected_head=HEAD,
    )

    assert authorization["status"] == AUTHORIZED_STATUS
    assert authorization["generation_run_limit"] == 1
    assert authorization["expected_head"] == HEAD
    assert authorization["corpus_sha256"] == baseline["corpus"]["sha256"]
    assert authorization["policy_sha256"] == baseline["policy"]["sha256"]
    assert authorization["product_owner_ack_sha256"] == canonical_sha256(ack)
    assert authorization["temporal_source_health"] == TEMPORAL_SOURCE_HEALTH
    assert authorization["p805_status"] == "BLOCKED_EXTERNAL_SOURCE"
    assert authorization["provider_execution_authorized"] is True
    assert authorization["external_actions"] is False


def test_ack_cannot_be_self_approved_by_known_automation_subject() -> None:
    baseline = _baseline()
    with pytest.raises(OutageQualityBindingBlocked) as caught:
        validate_product_owner_ack(
            _ack(subject="opencode"),
            baseline=baseline,
            expected_head=HEAD,
        )
    assert caught.value.code == "BLOCKED_PRODUCT_OWNER_ACK_NOT_AUTHORIZABLE"


def test_ack_is_bound_to_exact_head() -> None:
    baseline = _baseline()
    wrong = "a" * 40
    with pytest.raises(OutageQualityBindingBlocked) as caught:
        validate_product_owner_ack(
            _ack(head=wrong),
            baseline=baseline,
            expected_head=HEAD,
        )
    assert caught.value.code == "BLOCKED_PRODUCT_OWNER_ACK_NOT_AUTHORIZABLE"


def test_ack_is_bound_to_exact_corpus_and_policy() -> None:
    baseline = _baseline()
    value = _ack()
    value["corpus_sha256"] = "0" * 64
    with pytest.raises(OutageQualityBindingBlocked) as caught:
        validate_product_owner_ack(value, baseline=baseline, expected_head=HEAD)
    assert caught.value.code == "BLOCKED_PRODUCT_OWNER_ACK_NOT_AUTHORIZABLE"

    value = _ack()
    value["policy_sha256"] = "1" * 64
    with pytest.raises(OutageQualityBindingBlocked) as caught:
        validate_product_owner_ack(value, baseline=baseline, expected_head=HEAD)
    assert caught.value.code == "BLOCKED_PRODUCT_OWNER_ACK_NOT_AUTHORIZABLE"


def test_stale_ack_is_rejected() -> None:
    baseline = _baseline()
    now = datetime(2026, 8, 25, 7, 0, tzinfo=UTC)
    value = _ack(when=now - timedelta(hours=25))
    with pytest.raises(OutageQualityBindingBlocked) as caught:
        validate_product_owner_ack(
            value,
            baseline=baseline,
            expected_head=HEAD,
            now=now,
        )
    assert caught.value.code == "BLOCKED_PRODUCT_OWNER_ACK_STALE"


def test_future_ack_is_rejected() -> None:
    baseline = _baseline()
    now = datetime(2026, 8, 25, 7, 0, tzinfo=UTC)
    value = _ack(when=now + timedelta(minutes=6))
    with pytest.raises(OutageQualityBindingBlocked) as caught:
        validate_product_owner_ack(
            value,
            baseline=baseline,
            expected_head=HEAD,
            now=now,
        )
    assert caught.value.code == "BLOCKED_PRODUCT_OWNER_ACK_FROM_FUTURE"


def test_authorization_tamper_is_blocked() -> None:
    baseline = _baseline()
    ack = _ack()
    authorization = build_outage_authorization(
        baseline=baseline,
        ack=ack,
        expected_head=HEAD,
    )
    authorization["generation_run_limit"] = 2
    with pytest.raises(OutageQualityBindingBlocked) as caught:
        validate_outage_authorization(
            authorization,
            baseline=baseline,
            ack=ack,
            expected_head=HEAD,
        )
    assert caught.value.code == "BLOCKED_OUTAGE_AUTHORIZATION_INVALID"


def test_ack_consumption_is_atomic_and_one_shot(tmp_path: Path) -> None:
    ack_path = tmp_path / "product-owner-ack.json"
    ack = _ack()
    ack_path.write_text(json.dumps(ack), encoding="utf-8")
    digest = canonical_sha256(ack)

    marker = consume_ack_once(ack_path, ack_sha256=digest)
    assert marker == acknowledgement_consumption_marker(ack_path)
    assert marker.is_file()
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["ack_sha256"] == digest
    assert payload["generation_run_limit"] == 1

    with pytest.raises(OutageQualityBindingBlocked) as caught:
        consume_ack_once(ack_path, ack_sha256=digest)
    assert caught.value.code == "BLOCKED_PRODUCT_OWNER_ACK_ALREADY_CONSUMED"


def test_execute_outage_authorized_once_starts_exactly_one_runner(tmp_path: Path) -> None:
    baseline = _baseline()
    ack = _ack()
    authorization = build_outage_authorization(
        baseline=baseline,
        ack=ack,
        expected_head=HEAD,
    )
    calls: list[list[str]] = []

    def fake_runner(command, **kwargs):
        calls.append(list(command))
        assert kwargs["cwd"] == tmp_path
        assert kwargs["check"] is False
        assert kwargs["capture_output"] is True
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    result = execute_outage_authorized_once(
        authorization,
        ["python", "-m", "scripts.arv001.run_complete_corpus_acceptance"],
        baseline=baseline,
        ack=ack,
        expected_head=HEAD,
        env={},
        cwd=tmp_path,
        runner=fake_runner,
    )
    assert result.returncode == 0
    assert len(calls) == 1


def test_invalid_authorization_prevents_runner_start(tmp_path: Path) -> None:
    baseline = _baseline()
    ack = _ack()
    authorization = build_outage_authorization(
        baseline=baseline,
        ack=ack,
        expected_head=HEAD,
    )
    authorization["external_actions"] = True
    calls = 0

    def fake_runner(command, **kwargs):
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    with pytest.raises(OutageQualityBindingBlocked) as caught:
        execute_outage_authorized_once(
            authorization,
            ["python", "-m", "scripts.arv001.run_complete_corpus_acceptance"],
            baseline=baseline,
            ack=ack,
            expected_head=HEAD,
            env={},
            cwd=tmp_path,
            runner=fake_runner,
        )
    assert caught.value.code == "BLOCKED_OUTAGE_AUTHORIZATION_INVALID"
    assert calls == 0
