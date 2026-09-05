# BENCHMARK-PIPELINE-001

Shared benchmark contract and blind-evaluation workflow for Tender Agent discovery and document-analysis QA.

## Canonical contract

Contract version: `1.1.0`.

Machine-readable schema:
`benchmarks/pipeline/schema/1.1.0/benchmark-artifacts.schema.json`.

The previous `1.0.0` schema remains in the repository as historical evidence; new calibration artifacts use `1.1.0`.

Artifact classes:

- `case_manifest`
- `evaluator_bundle`
- `blind_discovery_label`
- `blind_document_truth`
- `frozen_label`
- `tender_agent_output_ref`
- `normalized_sut_output`
- `comparison_result`
- `review_state`
- `aggregate_scorecard`

Review states are explicit and machine-readable:

- `AI_CURATED_SILVER`
- `NEEDS_REVIEW`
- `HUMAN_VERIFIED_GOLD`

## Anti-circularity invariant

The enforced order is:

`public source bundle -> evaluator bundle -> blind labels -> freeze -> Tender Agent output -> comparator -> review routing`

The evaluator bundle is reconstructed from source-only manifest fields. SUT-derived keys such as ranking, scores, reports, extracted facts, artifact references and Tender Agent outputs are rejected recursively.

A freeze receipt binds all first-pass truth to immutable digests:

- source bundle;
- case manifest;
- evaluator bundle;
- blind discovery label;
- blind document truth;
- combined label set.

Tender Agent output is accepted only when it:

1. belongs to the same case and source bundle;
2. is explicitly bound to the frozen label-set digest;
3. has a normalized-output digest matching the referenced output;
4. was produced strictly after the blind-label freeze timestamp.

Changing the evaluator bundle, label, truth or manifest after freeze fails validation rather than silently changing benchmark truth.

## Discovery and document semantics

Discovery labels are exactly:

- `RELEVANT`
- `PARTIALLY_RELEVANT`
- `IRRELEVANT`
- `UNCLEAR`

`UNCLEAR` is not scored as a discovery error. Document truth supports:
`ASSERTED`, `UNKNOWN`, `INSUFFICIENT_EVIDENCE`, and `CONFLICTING_EVIDENCE`.

The deterministic comparator records:

- discovery exact match/mismatch or `NOT_SCORABLE`;
- document TP/FP/FN;
- contradictions;
- missed asserted facts;
- correct abstentions;
- unsupported/unresolved assertions;
- unlabeled SUT extras;
- precision, recall and F1.

Evaluator abstention is not converted into false benchmark certainty: an assertion against `UNKNOWN`, `INSUFFICIENT_EVIDENCE` or conflicting truth is marked unresolved rather than automatically counted as a false positive. Unlabeled SUT extras are unscored. Material unresolved assertions are routed for review.

A mechanically classifiable Tender Agent error (for example, a wrong frozen fact value) is scored as a SUT error but does **not** by itself invalidate a high-confidence benchmark label. This separation prevents the tested system from poisoning the independent truth set.

## Review routing

`NEEDS_REVIEW` is used for benchmark-quality uncertainty, including:

- evaluator confidence below threshold;
- material source conflict;
- weak source provenance;
- material `UNKNOWN` / `INSUFFICIENT_EVIDENCE`;
- material disagreement that cannot be mechanically classified;
- schema/consistency failure.

Otherwise the independently labeled case remains `AI_CURATED_SILVER`. Only explicit Product Owner approval can create `HUMAN_VERIFIED_GOLD`; promotion changes review metadata, not frozen source truth.

## CLI and batchability

The repository CLI is `scripts/benchmark_pipeline.py`.

It supports contract validation, source-file verification, blind-bundle preparation, label freeze, comparison, review routing, Product Owner promotion, scorecard generation and batch comparison.

A batch case directory uses:

```text
case_manifest.json
evaluator_bundle.json
blind_discovery_label.json
blind_document_truth.json
frozen_label.json
tender_agent_output_ref.json
normalized_sut_output.json
comparison_result.json        # generated
review_state.json              # generated
```

`batch-compare` processes already-frozen cases without Product Owner per-case orchestration and writes an aggregate scorecard. It does not collect procurements or perform external procurement actions.

## Calibration gate

Repository tests intentionally exercise only three workflow calibration paths:

1. matching, high-confidence source truth -> `AI_CURATED_SILVER` -> explicit Product Owner gold promotion;
2. low-confidence/insufficient source evidence plus material unclassified SUT assertions -> `NEEDS_REVIEW`;
3. mechanically classifiable Tender Agent error -> scored SUT failure while independent truth remains `AI_CURATED_SILVER`.

These are synthetic workflow fixtures, not procurement ground truth.

Do **not** scale to 30–50 procurements yet.

Before corpus growth, run the same contract on 1–3 real public procurement bundles. The intended seed set is the two previously reviewed Cybox/SciBox procurements and the RSL procurement, but their original public source materials must be re-imported through the accepted Tender Agent path. Previous prose conclusions are calibration context only and must not be copied as benchmark truth.

## Local Mac mini boundary

GitHub/CI owns the contract, schemas, comparator, review logic, batch tooling and offline tests.

Mac mini/Codex is needed only where local execution is genuinely required:

- acquire the original public procurement artifacts through the accepted Tender Agent runtime/source path;
- compute and persist real file hashes/manifests;
- run the real Tender Agent **after** the independent label freeze;
- normalize/persist the actual runtime artifacts and execute the comparator on those 1–3 real cases.

The local runner is not a semantic source of truth and must not see or rewrite the blind evaluator answer on behalf of Tender Agent.
