# BENCHMARK-PIPELINE-001 (#52)

## Status

Implementation hardening and repository-side real-calibration preparation are complete on contract `1.1.0`; both GitHub/CI gates are **PASS**.

Canonical merges:

- PR `#56` — `BENCHMARK-PIPELINE-001: harden blind benchmark contract`;
  - merge SHA: `dec002926f0a996c537c854548e3636e905140ba`;
  - CI run `33982587200`: `completed / success`.
- PR `#57` — `BENCHMARK-PIPELINE-001: add safe real calibration Phase A`;
  - merge SHA: `0958505576cdcd8a7edeb0a5d4973bf07f43cf76`;
  - CI run `33985540698`: `completed / success`.

The only remaining acceptance gate is execution of the first real-source calibration on the Mac mini and independent evaluation of the generated source-only bundle. Do **not** start autonomous 30–50 procurement corpus growth yet.

The first calibration target is fixed to a real **44-FZ** Cybox/SciBox case so it can use the already accepted Mac mini public-source path without expanding source scope:

- primary: procurement `0848300045426000620` — МКУ «Служба кладбищ» Одинцовского городского округа, ИИ-ассистенты on the «Сайбокс» platform;
- fallback: another previously reviewed 44-FZ Cybox/SciBox case if the primary public bundle can no longer be acquired completely;
- RSL `32616312799` is **not** the first calibration case because it is 223-FZ and the accepted autonomous source path currently supports 44-FZ only. Adding a 223-FZ source path remains outside this task.

## Implemented in GitHub

- strict Draft 2020-12 JSON Schema for all benchmark artifacts;
- exact discovery labels required by #52: `RELEVANT`, `PARTIALLY_RELEVANT`, `IRRELEVANT`, `UNCLEAR`;
- source-bundle hashing and real source-file hash verification;
- source-only evaluator bundle with recursive SUT-leakage rejection;
- blind-label evidence/reference consistency checks;
- immutable freeze receipt binding manifest, evaluator bundle, discovery label and document truth hashes;
- Tender Agent output must be bound to the frozen label set and produced strictly after freeze;
- deterministic discovery/document comparator with explicit abstention and uncertainty semantics;
- mechanically classifiable SUT errors are scored without automatically invalidating benchmark truth;
- material unresolved assertions/unlabeled extras route to review instead of becoming guessed false positives;
- explicit `AI_CURATED_SILVER`, `NEEDS_REVIEW`, `HUMAN_VERIFIED_GOLD` transitions;
- Product Owner gold promotion requires explicit identity and approval note and does not rewrite frozen truth;
- deterministic CLI plus batch comparator/aggregate scorecard;
- focused workflow calibration tests;
- dedicated `scripts/prepare_benchmark_calibration_phase_a.py` helper for the first real case. It selects the exact registry number, explicitly forces `analyze_after_download=false`, rejects any pre-freeze analysis/recommendation leakage, copies exact source bytes, hashes them, validates the v1.1.0 manifest, builds the source-only evaluator bundle and packages only blind-evaluator inputs into a ZIP.

## Anti-circularity contract

Canonical order:

`public source bundle -> source-only evaluator bundle -> independent labels -> freeze -> Tender Agent output -> comparator -> review routing`

The following are fail-closed:

1. evaluator bundle contains ranking, scores, report/output references or other SUT-derived fields;
2. blind evidence points outside the frozen source bundle;
3. labels are created before evaluator-bundle preparation or changed after freeze;
4. manifest/evaluator/source digests change after freeze;
5. Tender Agent output is generated at/before freeze or against another source/label digest;
6. normalized runtime output does not match its declared digest;
7. Phase A detects a non-`not_started` analysis mode, a final recommendation, or analysis/LLM/fallback events before independent labels are frozen.

## Comparator and review-state rule

Benchmark quality and SUT quality are intentionally separated.

A high-confidence, source-grounded label remains `AI_CURATED_SILVER` even if Tender Agent makes a mechanically classifiable error; the comparator records the mismatch/contradiction as a SUT error. `NEEDS_REVIEW` is reserved for benchmark uncertainty or disagreements that cannot safely be classified without semantic review.

This prevents circularity where Tender Agent's own failure could cause its independent truth to be rewritten.

## GitHub/CI gates — PASS

Both #56 and #57 completed the normal repository CI successfully. The second gate includes the dedicated network-free Phase A tests plus the existing dependency-lock, security, migrations, quality, Redis, Postgres/R8 acceptance and Arvectum OS bridge jobs.

## Real calibration gate

Use **one case first**. Add a second or third only after inspecting the first end-to-end result.

### Phase A — local source preparation; STOP before SUT

With the Tender Agent backend already running on the Mac mini, fast-forward the local checkout to canonical `main` at or after `0958505576cdcd8a7edeb0a5d4973bf07f43cf76`, then run:

```bash
python3 scripts/prepare_benchmark_calibration_phase_a.py \
  --registry-number 0848300045426000620 \
  --backend-url http://127.0.0.1:8000
```

Expected successful marker:

`BENCHMARK_CALIBRATION_PHASE_A_READY`

Default case directory:

`company_agent_runs/benchmark_calibration/calibration-44fz-0848300045426000620/`

Blind evaluator package:

`company_agent_runs/benchmark_calibration/calibration-44fz-0848300045426000620-blind-evaluator-input.zip`

The ZIP contains only:

- `case_manifest.json`;
- `evaluator_bundle.json`;
- exact acquired public files under `source/**`.

The helper itself performs the accepted read-only 44-FZ search/intake, exact-registry selection, source-byte copy, raw SHA-256 hashing, manifest/source verification and evaluator-bundle packaging. It explicitly disables automatic Tender Agent analysis.

After the helper reports READY: **STOP. Do not call the analysis endpoint, do not create any SUT output and do not freeze labels. Return/upload the evaluator ZIP to the independent evaluator first.**

### Independent evaluator boundary

The independent evaluator creates:

- `blind_discovery_label.json`;
- `blind_document_truth.json`.

These must be source-grounded against the exact Phase A bundle. Prior prose reviews and prior Tender Agent reports are not benchmark truth and must not be used as evidence.

### Phase B — local freeze, SUT, comparator

Only after the independent labels exist:

1. validate and freeze them with `scripts/benchmark_pipeline.py freeze`;
2. run the real Tender Agent against the exact same frozen source bundle;
3. persist `normalized_sut_output.json` and `tender_agent_output_ref.json`, bound to the exact source digest and frozen label-set digest and timestamped strictly after freeze;
4. run `compare`;
5. run `route-review`;
6. return the complete case artifacts for Product Owner inspection.

## Local Mac mini boundary

Only local-machine/runtime work remains:

- start/use the already accepted Tender Agent backend on the Mac mini;
- execute the Phase A helper above against the real public source;
- return the generated evaluator ZIP;
- after independent labels are frozen, execute the real Tender Agent runtime and deterministic Phase B commands.

Contract design, schemas, semantic benchmark truth, comparator semantics, review routing, tests, source-only Phase A orchestration and batch tooling are already repository-owned and must not be reimplemented or semantically decided by the local runner.

## Exit criteria before corpus growth

Do not proceed to 30–50 cases until all are true:

- GitHub/CI gates remain green on canonical main;
- at least one and no more than three real calibration cases complete the exact blind order;
- no evaluator bundle contains SUT leakage;
- frozen digests detect tampering and source mismatch;
- schemas reject invalid/ambiguous artifacts fail-closed;
- comparator outcomes for abstention, contradictions, misses and unlabeled extras are sensible on real data;
- review states route uncertain/conflicting provenance to `NEEDS_REVIEW` and keep ordinary SUT errors separate;
- Product Owner can inspect final artifacts and explicitly promote verified cases to gold without rewriting source truth.
