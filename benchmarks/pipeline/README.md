# BENCHMARK-PIPELINE-001

This directory implements the shared benchmark contract for Discovery QA (#50)
and Document QA (#51).

## Non-negotiable ordering

The workflow is deliberately asymmetric:

1. collect an immutable bundle of original public procurement sources;
2. build a **blind evaluator bundle** containing source metadata only;
3. obtain independent source-only `blind_discovery_label` and
   `blind_document_truth`;
4. freeze both labels and persist their SHA-256 receipt;
5. only then run Tender Agent as the system under test;
6. normalize/reference the Tender Agent output;
7. compare deterministically;
8. route the case to `AI_CURATED_SILVER` or `NEEDS_REVIEW`;
9. only the Product Owner can explicitly promote a case to
   `HUMAN_VERIFIED_GOLD`.

The evaluator bundle must never contain Tender Agent ranking, extracted facts,
reports, score reasons, comparator output, or prior prose analysis. Historical
SciBox/RSL write-ups are calibration context only; they are **not** benchmark truth.
The seed cases are usable only after their original public materials are imported
through the accepted product collection path.

## Artifacts

Version `1.0.0` schemas live in `schemas/v1/`.

Required pipeline artifacts are:

- `case_manifest`
- `blind_discovery_label`
- `blind_document_truth`
- `tender_agent_output_ref`
- `comparison_result`
- `review_state`
- aggregate `scorecard`

The implementation also uses `evaluator_bundle`, `frozen_label`, and
`normalized_sut_output` contracts to make anti-circularity testable instead of
procedural folklore.

`source_bundle_sha256` is the canonical SHA-256 of the sorted
`(source_id, source-file-sha256)` pairs in the manifest. Every downstream artifact
is bound to that digest. The frozen receipt binds both blind labels. The
Tender Agent reference must name that frozen label-set digest and have a
`produced_at` timestamp strictly later than the freeze timestamp.

## Comparator v1

Discovery comparison is exact and deterministic. A benchmark decision of
`UNKNOWN` or `INSUFFICIENT_EVIDENCE` is intentionally not scored and is routed
for review.

Document truth is joined to normalized Tender Agent facts by stable `fact_id`.
For v1, asserted values are compared as canonical JSON without fuzzy matching.

- exact assertion -> true positive;
- missing/abstaining SUT assertion against asserted truth -> false negative;
- different asserted value -> contradiction (one FP + one FN);
- SUT assertion against truth marked unknown/insufficient/conflicting -> false positive;
- extra SUT facts that have no blind truth row are not silently declared false.
  They are `UNLABELED_EXTRA`; material asserted extras route to review.

This conservative rule avoids making incomplete benchmark labels look more
authoritative than their evidence.

## Review routing

`NEEDS_REVIEW` is automatic for low evaluator confidence, material unresolved
source conflict, material insufficient evidence, weak provenance, schema or
consistency failure, or a material disagreement that the v1 comparator cannot
classify mechanically. A mechanically classified SUT error does **not** by itself
invalidate an otherwise sound silver label.

Gold promotion is a separate explicit Product Owner action and records
`promoted_by`, `promoted_at`, the previous state, and an approval note.

## Commands

Examples assume the repository root:

```bash
uv run python scripts/benchmark_pipeline.py validate \
  --type case_manifest --input <case>/case_manifest.json

uv run python scripts/benchmark_pipeline.py prepare-blind \
  --manifest <case>/case_manifest.json \
  --source-root <case> \
  --output <case>/evaluator_bundle.json

# Independent evaluator creates labels from evaluator_bundle + referenced sources.

uv run python scripts/benchmark_pipeline.py freeze \
  --bundle <case>/evaluator_bundle.json \
  --discovery <case>/blind_discovery_label.json \
  --truth <case>/blind_document_truth.json \
  --output <case>/frozen_label.json

# Tender Agent may run only after the previous command succeeds.

uv run python scripts/benchmark_pipeline.py compare \
  --bundle <case>/evaluator_bundle.json \
  --discovery <case>/blind_discovery_label.json \
  --truth <case>/blind_document_truth.json \
  --freeze <case>/frozen_label.json \
  --sut-ref <case>/tender_agent_output_ref.json \
  --sut-output <case>/normalized_sut_output.json \
  --output <case>/comparison_result.json

uv run python scripts/benchmark_pipeline.py route-review \
  --comparison <case>/comparison_result.json \
  --discovery <case>/blind_discovery_label.json \
  --truth <case>/blind_document_truth.json \
  --output <case>/review_state.json
```

Do not scale to the intended 30–50 procurement corpus until 1–3 real calibration
cases have demonstrated that bundle isolation, frozen hashes, schemas,
comparator classifications, and review-state transitions are correct.
