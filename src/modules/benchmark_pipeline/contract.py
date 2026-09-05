from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


CONTRACT_VERSION = "1.1.0"
SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "benchmarks"
    / "pipeline"
    / "schema"
    / CONTRACT_VERSION
    / "benchmark-artifacts.schema.json"
)


class BenchmarkContractError(ValueError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_schema() -> dict[str, Any]:
    try:
        return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BenchmarkContractError(f"benchmark schema not found: {SCHEMA_PATH}") from exc


def validate_artifact(kind: str, artifact: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        raise BenchmarkContractError(f"{kind} must be an object")

    schema = _load_schema()
    defs = schema.get("$defs", {})
    if kind not in defs:
        raise BenchmarkContractError(f"unknown benchmark artifact kind: {kind}")

    validator = Draft202012Validator(
        {"$schema": schema["$schema"], "$defs": defs, "$ref": f"#/$defs/{kind}"},
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(artifact), key=lambda err: list(err.absolute_path))
    if errors:
        rendered: list[str] = []
        for error in errors:
            path = ".".join(str(part) for part in error.absolute_path) or "<root>"
            rendered.append(f"{path}: {error.message}")
        raise BenchmarkContractError(f"{kind} contract violation: " + "; ".join(rendered))
    return artifact


def source_bundle_sha256(documents: list[dict[str, Any]]) -> str:
    identity = [
        {"path": document["path"], "sha256": document["sha256"]}
        for document in sorted(documents, key=lambda item: item["path"])
    ]
    return canonical_sha256(identity)


def validate_case_manifest_consistency(manifest: dict[str, Any]) -> dict[str, Any]:
    validate_artifact("case_manifest", manifest)
    paths = [document["path"] for document in manifest["documents"]]
    if len(paths) != len(set(paths)):
        raise BenchmarkContractError("case_manifest contains duplicate document paths")
    for path in paths:
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts:
            raise BenchmarkContractError(
                f"case_manifest document path must stay relative to source root: {path}"
            )
    expected = source_bundle_sha256(manifest["documents"])
    if manifest["source_bundle_sha256"] != expected:
        raise BenchmarkContractError(
            "case_manifest.source_bundle_sha256 must equal the canonical digest "
            "of sorted document path/sha256 pairs"
        )
    return manifest


def verify_manifest_source_files(
    manifest: dict[str, Any],
    source_root: str | Path,
) -> None:
    validate_case_manifest_consistency(manifest)
    root = Path(source_root).resolve()
    for document in manifest["documents"]:
        path = (root / document["path"]).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise BenchmarkContractError(
                f"document path escapes source root: {document['path']}"
            ) from exc
        if not path.is_file():
            raise BenchmarkContractError(f"missing source file: {document['path']}")
        actual = file_sha256(path)
        if actual != document["sha256"]:
            raise BenchmarkContractError(
                f"source hash mismatch for {document['path']}: "
                f"expected {document['sha256']}, got {actual}"
            )


def load_artifact(path: str | Path, kind: str) -> dict[str, Any]:
    artifact = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_artifact(kind, artifact)
    return artifact


def write_artifact(path: str | Path, artifact: dict[str, Any], kind: str) -> None:
    validate_artifact(kind, artifact)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
