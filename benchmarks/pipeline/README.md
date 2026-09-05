# BENCHMARK-PIPELINE-001

Shared benchmark contract and blind-evaluation workflow for Tender Agent discovery and document-analysis QA.

## Contract

Contract version: `1.0.0`.

Machine-readable schema: `benchmarks/pipeline/schema/v1/benchmark-artifacts.schema.json`.

Artifact classes:

- `case_manifest`
- `blind_discovery_label`
- `blind_document_truth`
- `tender_agent_output_ref`
- `comparison_result`
- `review_state`
- `aggregate_scorecard`

Review states are machine-readable and mutually explicit:

- `AI_CURATED_SILVER`
- `NEEDS_REVIEW`
- `HUMAN_VERIFIED_GOLD`

## Anti-circularity invariant

The workflow enforces this order in code:

`public source bundle -> evaluator bundle -> freeze blind labels -> attach Tender Agent output -> compare -> route review`

`BenchmarkCaseWorkflow.attach_sut_output()` rejects output before label freeze. `evaluator_bundle()` is reconstructed only from `case_manifest` source fields and is unavailable after the first-pass labels are frozen. The evaluator bundle therefore has no Tender Agent ranking, extracted facts, output refs, score reasons or comparator result.

The frozen discovery/document labels receive immutable-content hashes (`freeze_hash`). Human gold promotion changes only `review_state`; it does not rewrite the frozen source truth.

## Comparator

`src/modules/benchmark_pipeline/comparator.py` provides a deterministic first comparator:

- discovery exact-label match and optional ranking delta;
- document TP/FP/FN;
- unsupported SUT claims;
- same-field contradictions;
- missed asserted truth fields;
- aggregate discovery/document scorecard.

Abstained evaluator facts (`UNKNOWN`, `INSUFFICIENT_EVIDENCE`) are not counted as false negatives and are never treated as asserted truth.

## Review routing

A compared case is routed to `NEEDS_REVIEW` when any implemented rule applies:

- discovery confidence is below the configured threshold;
- document-truth confidence is below threshold;
- unresolved source conflict is declared in the manifest;
- provenance is insufficient;
- comparator reports material disagreement;
- comparator/schema validation reports failure.

Otherwise the case remains `AI_CURATED_SILVER` until explicit Product Owner verification. `promote_to_gold()` requires Product Owner reviewer metadata and preserves the frozen label/truth hashes.

## Calibration scope

The automated tests exercise three small calibration paths only:

1. matching high-confidence case -> `AI_CURATED_SILVER`;
2. low-confidence/material-disagreement case -> `NEEDS_REVIEW`;
3. matching case followed by explicit Product Owner promotion -> `HUMAN_VERIFIED_GOLD` without rewriting frozen truth.

These are workflow calibration fixtures, not procurement ground truth. The two Cybox cases and the RSL procurement must not be imported as benchmark evidence until their original public-source materials are acquired through the accepted product path, normalized into `case_manifest` bundles and re-labeled blind under this contract.

Do not scale to 30–50 procurements until the calibration gate confirms anti-circularity, schema validity, comparator behavior and review-state transitions on real imported source bundles.

## Local runner boundary

GitHub-hosted implementation and pure/offline contract tests belong in the repository/CI. Local Mac mini execution is required only for accepted-path source acquisition and Tender Agent runtime execution against real calibration procurements. The local runner is not a semantic source of truth.
