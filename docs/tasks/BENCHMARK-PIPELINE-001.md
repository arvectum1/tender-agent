# BENCHMARK-PIPELINE-001 (#52)

## Status

Implementation hardening is complete on contract `1.1.0` and the GitHub/CI gate is **PASS**.

Canonical merge:

- PR `#56` — `BENCHMARK-PIPELINE-001: harden blind benchmark contract`;
- `main` merge SHA: `dec002926f0a996c537c854548e3636e905140ba`;
- pull-request CI run `33982587200`: `completed / success`.

The only remaining acceptance gate is the first real-source calibration on the Mac mini. Do **not** start autonomous 30–50 procurement corpus growth yet.

The first calibration target is now fixed to a real **44-FZ** Cybox/SciBox case so it can use the already accepted Mac mini public-source path without expanding source scope:

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
- focused calibration tests for the three required workflow classes.

## Anti-circularity contract

Canonical order:

`public source bundle -> source-only evaluator bundle -> independent labels -> freeze -> Tender Agent output -> comparator -> review routing`

The following are fail-closed:

1. evaluator bundle contains ranking, scores, report/output references or other SUT-derived fields;
2. blind evidence points outside the frozen source bundle;
3. labels are created before evaluator-bundle preparation or changed after freeze;
4. manifest/evaluator/source digests change after freeze;
5. Tender Agent output is generated at/before freeze or against another source/label digest;
6. normalized runtime output does not match its declared digest.

## Comparator and review-state rule

Benchmark quality and SUT quality are intentionally separated.

A high-confidence, source-grounded label remains `AI_CURATED_SILVER` even if Tender Agent makes a mechanically classifiable error; the comparator records the mismatch/contradiction as a SUT error. `NEEDS_REVIEW` is reserved for benchmark uncertainty or disagreements that cannot safely be classified without semantic review.

This prevents circularity where Tender Agent's own failure could cause its independent truth to be rewritten.

## GitHub/CI gate — PASS

Required repository checks are satisfied by the successful PR CI:

```bash
python -m pytest -q tests/test_benchmark_pipeline.py
python -m compileall -q src scripts
```

The normal repository CI also completed the existing dependency-lock, security, migrations, quality, Redis, Postgres/R8 acceptance and Arvectum OS bridge jobs successfully for the merged head.

## Real calibration gate

Use **one case first**. Add a second or third only after inspecting the first end-to-end result.

### Phase A — local source preparation; STOP before SUT

On the Mac mini:

1. fast-forward the local `tender-agent` checkout to canonical `main` at or after `dec002926f0a996c537c854548e3636e905140ba`;
2. acquire the exact public source/document bundle for procurement `0848300045426000620` through the accepted read-only Tender Agent 44-FZ source path;
3. persist the original acquired public artifacts under a dedicated benchmark case directory;
4. build `case_manifest.json` with real raw-byte SHA-256 hashes and the canonical `source_bundle_sha256`;
5. run `scripts/benchmark_pipeline.py prepare-blind` to create `evaluator_bundle.json`;
6. validate that the evaluator bundle contains only source metadata and no Tender Agent ranking, analysis, report, score, extracted facts or other SUT-derived fields;
7. package/provide the case source bundle plus `case_manifest.json` and `evaluator_bundle.json` to the independent evaluator;
8. **STOP. Do not run Tender Agent analysis and do not create any SUT output yet.**

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

Only local-machine/runtime work should be handed to Codex/OpenCode:

- accepted-path public-source acquisition/download;
- real local file hashes/manifests;
- preparation of the source-only evaluator bundle;
- real Tender Agent runtime execution **after** freeze;
- normalization/persistence of local runtime outputs;
- running the already-implemented comparator/review router on the real calibration bundle.

Contract design, schemas, semantic benchmark truth, comparator semantics, review routing, tests and batch tooling remain repository-owned / independent-evaluator-owned and must not be reimplemented or semantically decided by the local runner.

## Exit criteria before corpus growth

Do not proceed to 30–50 cases until all are true:

- GitHub/CI gate remains green on canonical main;
- at least one and no more than three real calibration cases complete the exact blind order;
- no evaluator bundle contains SUT leakage;
- frozen digests detect tampering and source mismatch;
- schemas reject invalid/ambiguous artifacts fail-closed;
- comparator outcomes for abstention, contradictions, misses and unlabeled extras are sensible on real data;
- review states route uncertain/conflicting provenance to `NEEDS_REVIEW` and keep ordinary SUT errors separate;
- Product Owner can inspect final artifacts and explicitly promote verified cases to gold without rewriting source truth.
