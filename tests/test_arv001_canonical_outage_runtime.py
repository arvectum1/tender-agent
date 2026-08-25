from __future__ import annotations

import argparse
import json
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from scripts.arv001 import run_outage_quality_acceptance_canonical_runtime as owner


HEAD = "a" * 40


def _namespace(**overrides):
    values = {
        "preflight_only": False,
        "launch": False,
        "worker": False,
        "inspect": False,
        "expected_head": None,
        "gguf_path": None,
        "llama_server_path": None,
        "candidate_root": None,
        "intake_root": None,
        "approved_policy": None,
        "baseline_descriptor": None,
        "product_owner_ack": None,
        "private_root": None,
        "request_file": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _request(root: Path) -> Path:
    request_path = root / owner._REQUEST_FILENAME
    payload = {
        "schema_version": owner.REQUEST_SCHEMA_VERSION,
        "expected_head": HEAD,
        "gguf_path": str(root / "model.gguf"),
        "llama_server_path": str(root / "llama-server"),
        "candidate_root": str(root / "candidate"),
        "intake_root": str(root / "intake"),
        "approved_policy": str(root / "policy.json"),
        "baseline_descriptor": str(root / "baseline.json"),
        "product_owner_ack": str(root / "ack.json"),
        "database_path": str(root / "acceptance.sqlite3"),
        "data_dir": str(root / "application-data"),
        "acceptance_output_root": str(root / "acceptance"),
        "binding_root": str(root / "binding"),
    }
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(request_path, 0o600)
    return request_path


def _patch_runtime(monkeypatch):
    monkeypatch.setattr(owner, "_repository_preflight", lambda _head: None)
    monkeypatch.setattr(
        owner,
        "_validate_runtime_assets",
        lambda _gguf, _binary: (
            Path("model.gguf"),
            Path("llama-server"),
            {"gguf_sha256": "g"},
            {"binary_sha256": "b"},
        ),
    )

    @contextmanager
    def fake_verified_runtime(**_kwargs):
        yield {"AI_CORP_LLM_MODEL": owner.EXPECTED_MODEL_ALIAS}

    monkeypatch.setattr(owner, "_verified_runtime", fake_verified_runtime)


def test_preflight_only_never_touches_ack_or_outage_runner(monkeypatch, capsys):
    _patch_runtime(monkeypatch)

    def forbidden_ack_call(_path):
        raise AssertionError("preflight must not inspect or consume an acknowledgement")

    monkeypatch.setattr(
        owner, "acknowledgement_consumption_marker", forbidden_ack_call
    )

    result = owner._preflight_only(
        _namespace(
            preflight_only=True,
            expected_head=HEAD,
            gguf_path=Path("model.gguf"),
            llama_server_path=Path("llama-server"),
        )
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PRE_PROVIDER_RUNTIME_VERIFIED"
    assert payload["provider_generation_calls"] == 0
    assert payload["acknowledgement_touched"] is False
    assert payload["outage_runner_invocations"] == 0


def test_launch_detaches_worker_from_foreground_caller(monkeypatch, tmp_path, capsys):
    ack = tmp_path / "ack.json"
    ack.write_text("{}", encoding="utf-8")
    private_root = tmp_path / "execution"

    monkeypatch.setattr(owner, "_repository_preflight", lambda _head: None)
    monkeypatch.setattr(
        owner,
        "_validate_runtime_assets",
        lambda _gguf, _binary: (
            Path("model.gguf"),
            Path("llama-server"),
            {"gguf_sha256": "g"},
            {"binary_sha256": "b"},
        ),
    )
    monkeypatch.setattr(
        owner,
        "acknowledgement_consumption_marker",
        lambda path: path.parent / "not-consumed",
    )
    captured = {}

    class FakeProcess:
        pid = 4321

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(owner.subprocess, "Popen", fake_popen)

    result = owner._launch(
        _namespace(
            launch=True,
            expected_head=HEAD,
            gguf_path=tmp_path / "model.gguf",
            llama_server_path=tmp_path / "llama-server",
            candidate_root=tmp_path / "candidate",
            intake_root=tmp_path / "intake",
            approved_policy=tmp_path / "policy.json",
            baseline_descriptor=tmp_path / "baseline.json",
            product_owner_ack=ack,
            private_root=private_root,
        )
    )

    assert result == 0
    assert captured["kwargs"]["stdin"] == owner.subprocess.DEVNULL
    assert captured["kwargs"]["stdout"] == owner.subprocess.DEVNULL
    assert captured["kwargs"]["stderr"] == owner.subprocess.DEVNULL
    assert captured["kwargs"]["start_new_session"] is True
    assert captured["kwargs"]["close_fds"] is True
    assert "--worker" in captured["command"]
    assert (
        "scripts.arv001.run_outage_quality_acceptance_canonical_runtime"
        in captured["command"]
    )
    assert stat_mode(private_root) == 0o700
    assert stat_mode(private_root / owner._REQUEST_FILENAME) == 0o600
    output = json.loads(capsys.readouterr().out)
    assert output["acknowledgement_consumed_by_launcher"] is False
    assert output["outage_runner_invocations_by_launcher"] == 0


def test_worker_runs_outage_child_once_without_wrapper_timeout(monkeypatch, tmp_path):
    root = tmp_path / "execution"
    root.mkdir(mode=0o700)
    request_path = _request(root)
    _patch_runtime(monkeypatch)

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "status": "QUALITY_ACCEPTANCE_COMPLETE_UNDER_EXTERNAL_SOURCE_BLOCKER",
                    "marker": "ARV-001_QUALITY_ONLY_UNDER_EXTERNAL_SOURCE_BLOCKER_COMPLETE",
                    "acknowledgement_consumed": True,
                    "acceptance_invocations": 1,
                    "controlled_invocation_count": 1,
                    "execution_count": 2,
                    "repeat_identity_verified": True,
                    "artifact_hashes": {"manifest": "b" * 64},
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(owner.subprocess, "run", fake_run)

    result = owner._worker(_namespace(worker=True, request_file=request_path))

    assert result == 0
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert "scripts.arv001.run_outage_quality_acceptance" in command
    assert "timeout" not in kwargs
    state = json.loads((root / owner._STATE_FILENAME).read_text(encoding="utf-8"))
    assert state["state"] == "completed"
    assert state["outage_runner_invocations"] == 1
    assert state["result"]["execution_count"] == 2
    assert state["result"]["repeat_identity_verified"] is True


def test_worker_failure_is_terminal_and_not_retried(monkeypatch, tmp_path):
    root = tmp_path / "execution"
    root.mkdir(mode=0o700)
    request_path = _request(root)
    _patch_runtime(monkeypatch)

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=3,
            stdout=json.dumps(
                {
                    "status": "FAIL_CLOSED",
                    "failure_code": "provider_transient_failure",
                    "acknowledgement_consumed": True,
                    "acceptance_invocations": 1,
                }
            ),
            stderr="provider_transient_failure\n",
        )

    monkeypatch.setattr(owner.subprocess, "run", fake_run)

    result = owner._worker(_namespace(worker=True, request_file=request_path))

    assert result == 3
    assert len(calls) == 1
    state = json.loads((root / owner._STATE_FILENAME).read_text(encoding="utf-8"))
    assert state["state"] == "failed"
    assert state["sanitized_failure_code"] == "provider_transient_failure"
    assert state["outage_runner_invocations"] == 1


def test_safe_child_payload_drops_private_or_unknown_fields():
    payload = owner._safe_child_payload(
        json.dumps(
            {
                "status": "FAIL_CLOSED",
                "failure_code": "provider_transient_failure",
                "private_path": "/private/corpus/secret.pdf",
                "prompt": "secret tender text",
            }
        )
    )

    assert payload == {
        "status": "FAIL_CLOSED",
        "failure_code": "provider_transient_failure",
    }


def stat_mode(path: Path) -> int:
    return os.stat(path).st_mode & 0o777
