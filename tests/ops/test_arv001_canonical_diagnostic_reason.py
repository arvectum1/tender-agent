from __future__ import annotations

import pytest

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


def test_safe_machine_reason_prefers_stable_code_attribute() -> None:
    class StableError(RuntimeError):
        code = "prepared_document_identity_mismatch"

    assert (
        diagnostic._safe_machine_reason(StableError("/private/path"), "fallback")
        == "prepared_document_identity_mismatch"
    )


def test_safe_machine_reason_redacts_arbitrary_message_to_class() -> None:
    result = diagnostic._safe_machine_reason(
        ValueError("/private/secret/path"), "request_reconstruction_failed"
    )

    assert result == "request_reconstruction_failed:valueerror"
    assert "/private" not in result


def test_descriptor_wrapper_converts_unexpected_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        diagnostic,
        "_ORIGINAL_PARSE_PRIVATE_DESCRIPTOR",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("/private/path")),
    )

    with pytest.raises(RuntimeError, match="^private_descriptor_parse_failed:valueerror$"):
        diagnostic.diagnostic_parse_private_descriptor("unused")


def test_reconstruction_wrapper_preserves_safe_repository_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        diagnostic,
        "_ORIGINAL_RECONSTRUCT_REQUESTS",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("prepared_tender_binding_mismatch")
        ),
    )

    with pytest.raises(RuntimeError, match="^prepared_tender_binding_mismatch$"):
        diagnostic.diagnostic_reconstruct_actual_batch_requests("unused")
