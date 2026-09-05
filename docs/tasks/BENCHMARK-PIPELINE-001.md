# BENCHMARK-PIPELINE-001 (#52)

## Status

Implementation hardening is complete in GitHub on contract `1.1.0`. The real-source calibration gate remains pending local Mac mini execution.

Do not start autonomous 30–50 procurement corpus growth yet.

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

## GitHub/CI gate

Required repository checks:

```bash
python -m pytest -q tests/test_benchmark_pipeline.py
python -m compileall -q src scripts
```

The normal repository CI additionally runs the full test suite and existing quality/security gates.

## Real 1–3 case calibration gate

Use at most 1–3 cases before scaling. Intended seeds:

- Cybox/SciBox calibration A;
- Cybox/SciBox calibration B;
- RSL procurement.

For each case:

1. import original public source materials through the accepted Tender Agent source path;
2. build `case_manifest.json` with real hashes;
3. prepare and verify the source-only evaluator bundle;
4. create independent source-grounded discovery/document labels without Tender Agent output;
5. freeze labels;
6. only then run the real Tender Agent against the same source bundle;
7. persist normalized output/ref with frozen label/source digests;
8. run comparator and review routing;
9. inspect anti-circularity, schema behavior, comparator classifications and review state.

Previous prose reviews must not be copied as truth. They may only identify which procurement to re-import.

## Local Mac mini boundary

Only local-machine/runtime work should be handed to Codex/OpenCode:

- accepted-path public-source acquisition/download;
- real local file hashes/manifests;
- real Tender Agent runtime execution after freeze;
- normalization/persistence of local runtime outputs;
- running the already-implemented comparator on the 1–3 real calibration bundles.

Contract design, schemas, comparator semantics, review routing, tests and batch tooling remain repository-owned and should not be reimplemented locally.

## Exit criteria before corpus growth

Do not proceed to 30–50 cases until all are true:

- CI passes on the hardened implementation;
- at least one and no more than three real calibration cases complete the exact blind order;
- no evaluator bundle contains SUT leakage;
- frozen digests detect tampering and source mismatch;
- schemas reject invalid/ambiguous artifacts fail-closed;
- comparator outcomes for abstention, contradictions, misses and unlabeled extras are sensible on real data;
- review states route uncertain/conflicting provenance to `NEEDS_REVIEW` and keep ordinary SUT errors separate;
- Product Owner can inspect final artifacts and explicitly promote verified cases to gold without rewriting source truth.
