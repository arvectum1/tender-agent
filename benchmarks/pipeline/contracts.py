from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_VERSION = "1.0.0"
SCHEMA_DIR = Path(__file__).parent / "schemas" / "v1"

SCHEMA_FILES = {
    "case_manifest": "case_manifest.schema.json",
    "evaluator_bundle": "evaluator_bundle.schema.json",
    "blind_discovery_label": "blind_discovery_label.schema.json",
    "blind_document_truth": "blind_document_truth.schema.json",
    "frozen_label": "frozen_label.schema.json",
    "tender_agent_output_ref": "tender_agent_output_ref.schema.json",
    "normalized_sut_output": "normalized_sut_output.schema.json",
    "comparison_result": "comparison_result.schema.json",
    "review_state": "review_state.schema.json",
    "scorecard": "scorecard.schema.json",
}


class ContractError(ValueError):
    """Raised when a benchmark artifact violates its versioned contract."""


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


def load_schema(artifact_type: str) -> dict[str, Any]:
    try:
        filename = SCHEMA_FILES[artifact_type]
    except KeyError as exc:
        raise ContractError(f"unknown artifact type: {artifact_type}") from exc
    return json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))


def source_bundle_sha256(sources: list[dict[str, Any]]) -> str:
    identity = [
        {"source_id": source["source_id"], "sha256": source["sha256"]}
        for source in sorted(sources, key=lambda item: item["source_id"])
    ]
    return canonical_sha256(identity)


def validate_artifact(artifact_type: str, value: dict[str, Any]) -> None:
    schema = load_schema(artifact_type)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(value), key=lambda err: list(err.path))
    if not errors:
        return
    rendered = []
    for error in errors:
        path = ".".join(str(part) for part in error.absolute_path) or "<root>"
        rendered.append(f"{path}: {error.message}")
    raise ContractError(f"{artifact_type} contract violation: " + "; ".join(rendered))


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_case_manifest_consistency(manifest: dict[str, Any]) -> None:
    validate_artifact("case_manifest", manifest)
    source_ids = [source["source_id"] for source in manifest["sources"]]
    if len(source_ids) != len(set(source_ids)):
        raise ContractError("case_manifest contains duplicate source_id values")
    expected = source_bundle_sha256(manifest["sources"])
    if manifest["source_bundle_sha256"] != expected:
        raise ContractError(
            "case_manifest source_bundle_sha256 must equal the canonical digest "
            "of sorted source_id/sha256 pairs"
        )


def verify_manifest_source_files(manifest: dict[str, Any], source_root: str | Path) -> None:
    validate_case_manifest_consistency(manifest)
    root = Path(source_root)
    for source in manifest["sources"]:
        path = root / source["local_path"]
        if not path.is_file():
            raise ContractError(f"missing source file for {source['source_id']}: {path}")
        actual = file_sha256(path)
        if actual != source["sha256"]:
            raise ContractError(
                f"source hash mismatch for {source['source_id']}: expected "
                f"{source['sha256']}, got {actual}"
            )


def read_and_validate(path: str | Path, artifact_type: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_artifact(artifact_type, payload)
    return payload


def write_json(path: str | Path, value: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
