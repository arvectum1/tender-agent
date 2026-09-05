# BENCHMARK-PIPELINE-001 calibration runbook

This directory is the runbook for the first real calibration gate. It is **not** a 30–50 case corpus seed yet.

## Scope

Use only 1–3 real public procurement cases until anti-circularity, schemas, comparator classifications and review states have been inspected end-to-end.

Intended candidates are the two previously reviewed Cybox/SciBox procurements and the RSL procurement. Their previous prose reviews are not benchmark labels. Re-import original public source materials and regenerate truth blindly.

## Required files per case

```text
<case>/
  source/...                       # original acquired public artifacts
  case_manifest.json
  evaluator_bundle.json
  blind_discovery_label.json
  blind_document_truth.json
  frozen_label.json
  tender_agent_output_ref.json
  normalized_sut_output.json
  comparison_result.json           # generated after SUT execution
  review_state.json                # generated after comparison
```

## Exact order

### 1. Acquire sources and build manifest locally

Use the accepted Tender Agent source/runtime path on the Mac mini. Do not use old analysis output as source material.

The manifest must contain real SHA-256 hashes for every file and a `source_bundle_sha256` calculated under contract `1.1.0`.

### 2. Prepare the blind evaluator bundle

```bash
python scripts/benchmark_pipeline.py prepare-blind \
  --manifest <case>/case_manifest.json \
  --source-root <case> \
  --output <case>/evaluator_bundle.json
```

This command verifies local source-file hashes and creates only the source metadata the independent evaluator may see.

### 3. Independent evaluation

Give the evaluator the original source bundle plus `evaluator_bundle.json`, but **do not provide any Tender Agent ranking, extraction, report, scores or runtime output**.

Produce:

- `blind_discovery_label.json`
- `blind_document_truth.json`

Use `UNCLEAR`, `UNKNOWN`, `INSUFFICIENT_EVIDENCE` or `CONFLICTING_EVIDENCE` rather than guessing.

### 4. Freeze

```bash
python scripts/benchmark_pipeline.py freeze \
  --bundle <case>/evaluator_bundle.json \
  --discovery <case>/blind_discovery_label.json \
  --truth <case>/blind_document_truth.json \
  --output <case>/frozen_label.json
```

After this point, the blind labels are immutable benchmark input. Any change should fail digest verification.

### 5. Run Tender Agent locally

Only now run the real Tender Agent against the exact same source bundle. Persist a `normalized_sut_output.json` plus `tender_agent_output_ref.json` that binds:

- the source-bundle digest;
- the frozen label-set digest;
- the normalized-output digest;
- a runtime/version identifier;
- a `produced_at` timestamp strictly after freeze.

### 6. Compare

```bash
python scripts/benchmark_pipeline.py compare \
  --bundle <case>/evaluator_bundle.json \
  --discovery <case>/blind_discovery_label.json \
  --truth <case>/blind_document_truth.json \
  --freeze <case>/frozen_label.json \
  --sut-ref <case>/tender_agent_output_ref.json \
  --sut-output <case>/normalized_sut_output.json \
  --output <case>/comparison_result.json
```

### 7. Route review

```bash
python scripts/benchmark_pipeline.py route-review \
  --manifest <case>/case_manifest.json \
  --discovery <case>/blind_discovery_label.json \
  --truth <case>/blind_document_truth.json \
  --freeze <case>/frozen_label.json \
  --comparison <case>/comparison_result.json \
  --output <case>/review_state.json
```

Stop and inspect the first result before adding another calibration case.

## What to inspect

- no SUT-derived metadata in evaluator input;
- source, manifest, evaluator and labels remain digest-bound after freeze;
- invalid schemas or timestamps fail closed;
- evaluator abstention is not treated as asserted ground truth;
- ordinary SUT errors are scored without poisoning benchmark state;
- material unresolved claims route to `NEEDS_REVIEW`;
- high-confidence source-grounded truth can remain `AI_CURATED_SILVER`;
- `HUMAN_VERIFIED_GOLD` appears only after explicit Product Owner approval.

Only after the real 1–3 case gate succeeds should #52 proceed toward autonomous 30–50 case collection.
