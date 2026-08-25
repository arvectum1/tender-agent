from __future__ import annotations

from scripts.arv001 import full_pre_provider_canonical_diagnostic as diagnostic


def test_safe_runtime_reason_code_is_preserved() -> None:
    assert (
        diagnostic.canonical_exception_reason_code(
            RuntimeError("prepared_document_identity_mismatch"),
            "runtime_start",
        )
        == "prepared_document_identity_mismatch"
    )


def test_safe_child_phase_code_is_preserved() -> None:
    assert (
        diagnostic.canonical_exception_reason_code(
            RuntimeError("arv001_unexpected_exception:application_data:runtimeerror"),
            "runtime_start",
        )
        == "arv001_unexpected_exception:application_data:runtimeerror"
    )


def test_arbitrary_private_text_is_not_preserved() -> None:
    result = diagnostic.canonical_exception_reason_code(
        RuntimeError("/private/secret/path must not leak"),
        "runtime_start",
    )

    assert result == "runtime_start_failed"
    assert "/private/secret/path" not in result


def test_child_reason_with_filename_is_preserved() -> None:
    stderr = "required_intake_artifact_missing_or_unsafe:metadata.json\n"

    assert (
        diagnostic.canonical_safe_child_failure(stderr)
        == "required_intake_artifact_missing_or_unsafe:metadata.json"
    )


def test_child_reason_survives_trailing_noise() -> None:
    stderr = (
        "arv001_unexpected_exception:application_data:integrityerror\n"
        "warning\n"
    )

    assert (
        diagnostic.canonical_safe_child_failure(stderr)
        == "arv001_unexpected_exception:application_data:integrityerror"
    )


def test_child_private_path_is_redacted() -> None:
    stderr = "/private/secret/path\nwarning\n"

    assert diagnostic.canonical_safe_child_failure(stderr) == "application_persistence_failed"
