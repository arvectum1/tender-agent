#!/usr/bin/env python3
"""Durable canonical-runtime owner for governed ARV-001 outage acceptance.

The foreground launcher deliberately does not own the long-running model or
acceptance process.  A detached worker owns the approved llama-server for the
entire one-shot child invocation, so an interactive caller timing out cannot
tear down the runtime mid-batch.  The worker never retries the outage runner.

``--preflight-only`` is a zero-generation runtime check and does not read or
consume a product-owner acknowledgement.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.arv001 import full_pre_provider_canonical as canonical
from scripts.arv001.outage_quality_binding import acknowledgement_consumption_marker
from scripts.arv001.runtime_doctor import (
    ManagedLoopbackRuntime,
    ephemeral_runtime_environment,
    probe_zero_generation,
    scoped_environment,
    validate_effective_runtime_environment,
)
from src.modules.production_llm_analysis.batching import tokenizer_from_environment

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_SCHEMA_VERSION = "arv001-canonical-runtime-owner-v1"
REQUEST_SCHEMA_VERSION = "arv001-canonical-runtime-owner-request-v1"
EXPECTED_MODEL_ALIAS = "arvectum-gemma4-12b-it-qat-q4_0"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_SAFE_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,180}$")
_REQUEST_FILENAME = "canonical-runtime-request.json"
_STATE_FILENAME = "canonical-runtime-state.json"

_REQUEST_KEYS = {
    "schema_version",
    "expected_head",
    "gguf_path",
    "llama_server_path",
    "candidate_root",
    "intake_root",
    "approved_policy",
    "baseline_descriptor",
    "product_owner_ack",
    "database_path",
    "data_dir",
    "acceptance_output_root",
    "binding_root",
}

_SAFE_RESULT_KEYS = {
    "schema_version",
    "status",
    "failure_code",
    "marker",
    "temporal_source_health",
    "external_blocker_code",
    "p805_status",
    "quality_evidence_class",
    "expected_head",
    "baseline_id",
    "baseline_descriptor_sha256",
    "corpus_sha256",
    "policy_sha256",
    "product_owner_ack_sha256",
    "authorization_manifest_sha256",
    "acknowledgement_consumed",
    "acceptance_invocations",
    "controlled_invocation_count",
    "execution_count",
    "repeat_identity_verified",
    "artifact_hashes",
    "production_db_mutations",
    "old_arv003_mutations",
    "git_mutations",
    "external_actions",
    "manifest_sha256",
}


class CanonicalRuntimeOwnerBlocked(RuntimeError):
    """Fail-closed boundary with a repository-owned sanitized reason code."""

    def __init__(self, code: str) -> None:
        self.code = code if _SAFE_CODE.fullmatch(code) else "canonical_runtime_owner_failed"
        super().__init__(self.code)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Own the canonical local runtime for one governed ARV-001 outage run."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true")
    mode.add_argument("--launch", action="store_true")
    mode.add_argument("--worker", action="store_true")
    mode.add_argument("--inspect", action="store_true")

    parser.add_argument("--expected-head")
    parser.add_argument("--gguf-path", type=Path)
    parser.add_argument("--llama-server-path", type=Path)

    parser.add_argument("--candidate-root", type=Path)
    parser.add_argument("--intake-root", type=Path)
    parser.add_argument("--approved-policy", type=Path)
    parser.add_argument("--baseline-descriptor", type=Path)
    parser.add_argument("--product-owner-ack", type=Path)
    parser.add_argument("--private-root", type=Path)
    parser.add_argument("--request-file", type=Path)
    return parser.parse_args()


def _repository_preflight(expected_head: str) -> None:
    head = str(expected_head or "").strip().lower()
    if not _HEX40.fullmatch(head):
        raise CanonicalRuntimeOwnerBlocked("expected_head_invalid")
    try:
        actual = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip()
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=PROJECT_ROOT, text=True
        ).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=PROJECT_ROOT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CanonicalRuntimeOwnerBlocked("repository_preflight_unavailable") from exc
    if actual != head:
        raise CanonicalRuntimeOwnerBlocked("git_head_mismatch")
    if branch or dirty:
        raise CanonicalRuntimeOwnerBlocked("git_worktree_not_clean_detached")


def _outside_repository(path: Path, code: str, *, strict: bool = False) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=strict)
        repository = PROJECT_ROOT.resolve(strict=True)
    except OSError as exc:
        raise CanonicalRuntimeOwnerBlocked(code) from exc
    if resolved == repository or repository in resolved.parents:
        raise CanonicalRuntimeOwnerBlocked(code)
    return resolved


def _validate_runtime_assets(
    gguf_path: Path, llama_server_path: Path
) -> tuple[Path, Path, dict[str, str], dict[str, str]]:
    gguf = gguf_path.expanduser().resolve(strict=False)
    binary = llama_server_path.expanduser().resolve(strict=False)
    gguf_profile, gguf_errors = canonical._validate_approved_gguf(gguf)
    if gguf_errors or gguf_profile is None:
        raise CanonicalRuntimeOwnerBlocked(gguf_errors[0] if gguf_errors else "approved_gguf_invalid")
    binary_profile, binary_errors = canonical._validate_approved_llama_server(binary)
    if binary_errors or binary_profile is None:
        raise CanonicalRuntimeOwnerBlocked(
            binary_errors[0] if binary_errors else "approved_llama_server_invalid"
        )
    return gguf, binary, gguf_profile, binary_profile


def _runtime_probe(
    *, gguf: Path, binary: Path, gguf_profile: dict[str, str], binary_profile: dict[str, str]
) -> tuple[ManagedLoopbackRuntime, dict[str, str], Any]:
    runtime = ManagedLoopbackRuntime(
        binary=binary,
        gguf=gguf,
        timeout_seconds=120.0,
    )
    runtime.start()
    try:
        if runtime.port is None:
            raise CanonicalRuntimeOwnerBlocked("runtime_port_missing")
        environment_context = ephemeral_runtime_environment(
            port=runtime.port,
            binary_sha256=binary_profile["binary_sha256"],
            gguf_sha256=gguf_profile["gguf_sha256"],
            overrides={},
        )
        effective, private_env = environment_context.__enter__()
        errors = validate_effective_runtime_environment(effective, port=runtime.port)
        if errors:
            environment_context.__exit__(None, None, None)
            raise CanonicalRuntimeOwnerBlocked(errors[0])
        with scoped_environment(effective):
            tokenizer = tokenizer_from_environment()
            probe, probe_errors = probe_zero_generation(
                loopback_base_url=f"http://127.0.0.1:{runtime.port}",
                tokenizer_url=effective["ARV003_LLAMA_TOKENIZER_URL"],
                tokenizer_adapter=tokenizer,
                tokenizer_identity=effective["ARV003_TOKENIZER_IDENTITY"],
            )
        if probe_errors or probe is None:
            environment_context.__exit__(None, None, None)
            raise CanonicalRuntimeOwnerBlocked(
                probe_errors[0] if probe_errors else "zero_generation_probe_failed"
            )
        if (
            probe.get("models_probe_verified") is not True
            or probe.get("tokenizer_probe_verified") is not True
            or probe.get("tokenizer_persistent") is not True
            or probe.get("provider_generation_calls") != 0
        ):
            environment_context.__exit__(None, None, None)
            raise CanonicalRuntimeOwnerBlocked("zero_generation_probe_contract_invalid")
        # The caller owns both contexts after a successful probe.  Returning the
        # context object keeps the disposable environment alive for the child.
        return runtime, effective, environment_context
    except BaseException:
        runtime.stop()
        raise


def _close_runtime_probe(runtime: ManagedLoopbackRuntime, environment_context: Any) -> None:
    try:
        environment_context.__exit__(None, None, None)
    finally:
        runtime.stop()


def _preflight_only(args: argparse.Namespace) -> int:
    if args.expected_head is None or args.gguf_path is None or args.llama_server_path is None:
        raise CanonicalRuntimeOwnerBlocked("preflight_arguments_missing")
    _repository_preflight(args.expected_head)
    gguf, binary, gguf_profile, binary_profile = _validate_runtime_assets(
        args.gguf_path, args.llama_server_path
    )
    runtime, effective, environment_context = _runtime_probe(
        gguf=gguf,
        binary=binary,
        gguf_profile=gguf_profile,
        binary_profile=binary_profile,
    )
    try:
        body = {
            "schema_version": STATE_SCHEMA_VERSION,
            "status": "PRE_PROVIDER_RUNTIME_VERIFIED",
            "expected_head": args.expected_head,
            "model_alias": effective["AI_CORP_LLM_MODEL"],
            "models_probe_verified": True,
            "tokenizer_probe_verified": True,
            "tokenizer_persistent": True,
            "provider_generation_calls": 0,
            "acknowledgement_touched": False,
            "outage_runner_invocations": 0,
        }
        print(json.dumps(body, sort_keys=True))
        return 0
    finally:
        _close_runtime_probe(runtime, environment_context)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    staged = path.parent / f".{path.name}.partial.{os.getpid()}"
    try:
        staged.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        os.chmod(staged, 0o600)
        os.replace(staged, path)
    except OSError as exc:
        try:
            staged.unlink(missing_ok=True)
        except OSError:
            pass
        raise CanonicalRuntimeOwnerBlocked("private_state_write_failed") from exc


def _write_state(root: Path, *, state: str, **fields: Any) -> None:
    payload = {
        "schema_version": STATE_SCHEMA_VERSION,
        "state": state,
        **fields,
    }
    _atomic_json(root / _STATE_FILENAME, payload)


def _read_request(path: Path) -> tuple[Path, dict[str, str]]:
    request_path = _outside_repository(path, "worker_request_missing", strict=True)
    try:
        if request_path.is_symlink() or not request_path.is_file():
            raise CanonicalRuntimeOwnerBlocked("worker_request_unsafe")
        if stat.S_IMODE(request_path.stat().st_mode) != 0o600:
            raise CanonicalRuntimeOwnerBlocked("worker_request_mode_invalid")
        raw = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalRuntimeOwnerBlocked("worker_request_invalid") from exc
    if not isinstance(raw, dict) or set(raw) != _REQUEST_KEYS:
        raise CanonicalRuntimeOwnerBlocked("worker_request_schema_invalid")
    if raw.get("schema_version") != REQUEST_SCHEMA_VERSION:
        raise CanonicalRuntimeOwnerBlocked("worker_request_schema_invalid")
    if not all(isinstance(raw.get(key), str) and raw[key] for key in _REQUEST_KEYS):
        raise CanonicalRuntimeOwnerBlocked("worker_request_schema_invalid")
    return request_path.parent, {key: str(value) for key, value in raw.items()}


def _safe_child_payload(stdout: str) -> dict[str, Any]:
    try:
        parsed = json.loads(stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {key: parsed[key] for key in _SAFE_RESULT_KEYS if key in parsed}


def _safe_stderr_code(stderr: str) -> str:
    for raw in reversed(stderr.splitlines()):
        value = raw.strip()
        if _SAFE_CODE.fullmatch(value):
            return value
    return "outage_runner_failed_without_safe_reason"


def _outage_command(request: dict[str, str]) -> list[str]:
    return [
        sys.executable,
        "-m",
        "scripts.arv001.run_outage_quality_acceptance",
        "--baseline-descriptor",
        request["baseline_descriptor"],
        "--baseline-candidate-root",
        request["candidate_root"],
        "--baseline-intake-root",
        request["intake_root"],
        "--database-path",
        request["database_path"],
        "--initialize-database",
        "--data-dir",
        request["data_dir"],
        "--approved-policy",
        request["approved_policy"],
        "--acceptance-output-root",
        request["acceptance_output_root"],
        "--binding-root",
        request["binding_root"],
        "--product-owner-ack",
        request["product_owner_ack"],
        "--expected-head",
        request["expected_head"],
    ]


def _worker(args: argparse.Namespace) -> int:
    if args.request_file is None:
        raise CanonicalRuntimeOwnerBlocked("worker_request_missing")
    root, request = _read_request(args.request_file)
    try:
        _write_state(root, state="runtime_validation", expected_head=request["expected_head"])
        _repository_preflight(request["expected_head"])
        gguf, binary, gguf_profile, binary_profile = _validate_runtime_assets(
            Path(request["gguf_path"]), Path(request["llama_server_path"])
        )
        runtime, effective, environment_context = _runtime_probe(
            gguf=gguf,
            binary=binary,
            gguf_profile=gguf_profile,
            binary_profile=binary_profile,
        )
        try:
            _write_state(
                root,
                state="runtime_verified",
                expected_head=request["expected_head"],
                model_alias=effective["AI_CORP_LLM_MODEL"],
                models_probe_verified=True,
                tokenizer_probe_verified=True,
                tokenizer_persistent=True,
                provider_generation_calls_before_acceptance=0,
            )
            _write_state(
                root,
                state="acceptance_running",
                expected_head=request["expected_head"],
                outage_runner_invocations=1,
            )
            # Intentionally NO timeout here.  The repository provider policy owns
            # request latency; the detached worker owns the runtime until the
            # one permitted outage child reaches a terminal state.
            with scoped_environment(effective):
                completed = subprocess.run(
                    _outage_command(request),
                    cwd=PROJECT_ROOT,
                    env=os.environ.copy(),
                    text=True,
                    capture_output=True,
                    check=False,
                )
            result = _safe_child_payload(completed.stdout)
            terminal_state = "completed" if completed.returncode == 0 else "failed"
            _write_state(
                root,
                state=terminal_state,
                expected_head=request["expected_head"],
                outage_runner_invocations=1,
                child_return_code=completed.returncode,
                sanitized_failure_code=(
                    None
                    if completed.returncode == 0
                    else str(result.get("failure_code") or _safe_stderr_code(completed.stderr))
                ),
                result=result,
            )
            return 0 if completed.returncode == 0 else 3
        finally:
            _close_runtime_probe(runtime, environment_context)
    except CanonicalRuntimeOwnerBlocked as exc:
        _write_state(
            root,
            state="blocked",
            expected_head=request.get("expected_head"),
            sanitized_failure_code=exc.code,
            outage_runner_invocations=0,
        )
        return 2
    except Exception as exc:  # noqa: BLE001 - terminal state is sanitized.
        _write_state(
            root,
            state="failed",
            expected_head=request.get("expected_head"),
            sanitized_failure_code=f"runtime_owner_error:{type(exc).__name__}",
            outage_runner_invocations=0,
        )
        return 2


def _require_launch_arguments(args: argparse.Namespace) -> None:
    required = (
        "expected_head",
        "gguf_path",
        "llama_server_path",
        "candidate_root",
        "intake_root",
        "approved_policy",
        "baseline_descriptor",
        "product_owner_ack",
        "private_root",
    )
    if any(getattr(args, name) is None for name in required):
        raise CanonicalRuntimeOwnerBlocked("launch_arguments_missing")


def _launch(args: argparse.Namespace) -> int:
    _require_launch_arguments(args)
    assert args.private_root is not None
    assert args.expected_head is not None
    assert args.gguf_path is not None
    assert args.llama_server_path is not None
    assert args.candidate_root is not None
    assert args.intake_root is not None
    assert args.approved_policy is not None
    assert args.baseline_descriptor is not None
    assert args.product_owner_ack is not None

    _repository_preflight(args.expected_head)
    # Cheap identity validation happens before a detached worker can touch ack.
    _validate_runtime_assets(args.gguf_path, args.llama_server_path)

    root = _outside_repository(args.private_root, "private_root_inside_repository")
    if root.exists() or root.is_symlink():
        raise CanonicalRuntimeOwnerBlocked("private_root_already_exists")
    ack = _outside_repository(args.product_owner_ack, "product_owner_ack_missing", strict=True)
    if ack.is_symlink() or not ack.is_file():
        raise CanonicalRuntimeOwnerBlocked("product_owner_ack_unsafe")
    if acknowledgement_consumption_marker(ack).exists():
        raise CanonicalRuntimeOwnerBlocked("product_owner_ack_already_consumed")

    root.mkdir(parents=True, mode=0o700)
    os.chmod(root, 0o700)
    request = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "expected_head": args.expected_head,
        "gguf_path": str(args.gguf_path.expanduser().resolve(strict=False)),
        "llama_server_path": str(args.llama_server_path.expanduser().resolve(strict=False)),
        "candidate_root": str(args.candidate_root.expanduser().resolve(strict=False)),
        "intake_root": str(args.intake_root.expanduser().resolve(strict=False)),
        "approved_policy": str(args.approved_policy.expanduser().resolve(strict=False)),
        "baseline_descriptor": str(args.baseline_descriptor.expanduser().resolve(strict=False)),
        "product_owner_ack": str(ack),
        "database_path": str(root / "acceptance.sqlite3"),
        "data_dir": str(root / "application-data"),
        "acceptance_output_root": str(root / "acceptance"),
        "binding_root": str(root / "binding"),
    }
    request_path = root / _REQUEST_FILENAME
    _atomic_json(request_path, request)
    _write_state(root, state="worker_launching", expected_head=args.expected_head)

    command = [
        sys.executable,
        "-m",
        "scripts.arv001.run_outage_quality_acceptance_canonical_runtime",
        "--worker",
        "--request-file",
        str(request_path),
    ]
    try:
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as exc:
        _write_state(
            root,
            state="worker_launch_failed",
            expected_head=args.expected_head,
            sanitized_failure_code="worker_launch_failed",
        )
        raise CanonicalRuntimeOwnerBlocked("worker_launch_failed") from exc

    print(
        json.dumps(
            {
                "schema_version": STATE_SCHEMA_VERSION,
                "status": "ARV-001_CANONICAL_RUNTIME_WORKER_LAUNCHED",
                "expected_head": args.expected_head,
                "worker_pid": process.pid,
                "acknowledgement_consumed_by_launcher": False,
                "outage_runner_invocations_by_launcher": 0,
            },
            sort_keys=True,
        )
    )
    return 0


def _inspect(args: argparse.Namespace) -> int:
    if args.private_root is None:
        raise CanonicalRuntimeOwnerBlocked("inspect_private_root_missing")
    root = _outside_repository(args.private_root, "inspect_private_root_invalid", strict=True)
    state_path = root / _STATE_FILENAME
    try:
        if state_path.is_symlink() or not state_path.is_file():
            raise CanonicalRuntimeOwnerBlocked("runtime_state_missing")
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalRuntimeOwnerBlocked("runtime_state_invalid") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != STATE_SCHEMA_VERSION:
        raise CanonicalRuntimeOwnerBlocked("runtime_state_invalid")
    print(json.dumps(payload, sort_keys=True))
    return 0


def main() -> int:
    try:
        args = _arguments()
        if args.preflight_only:
            return _preflight_only(args)
        if args.launch:
            return _launch(args)
        if args.worker:
            return _worker(args)
        return _inspect(args)
    except CanonicalRuntimeOwnerBlocked as exc:
        print(
            json.dumps(
                {
                    "schema_version": STATE_SCHEMA_VERSION,
                    "status": "FAIL_CLOSED",
                    "failure_code": exc.code,
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
