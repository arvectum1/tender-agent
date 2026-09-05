# BENCHMARK-PIPELINE-001 (#52)

## Status

Phase 1 implemented in GitHub: benchmark contract, anti-circular blind workflow, deterministic comparator, review-state routing and calibration tests.

## Implemented

- versioned contract `1.0.0`;
- combined JSON Schema for all required artifacts;
- `BenchmarkCaseWorkflow` state machine;
- evaluator bundle built only from public-source manifest fields;
- label freeze hashes before Tender Agent output is accepted;
- deterministic discovery/document comparator;
- explicit `AI_CURATED_SILVER`, `NEEDS_REVIEW`, `HUMAN_VERIFIED_GOLD` routing;
- Product Owner gold promotion without rewriting frozen truth;
- aggregate scorecard;
- three small workflow calibration paths.

## Calibration gate

Do not expand the corpus to 30–50 procurements yet.

Before corpus growth, import 1–3 real calibration procurements into the same `case_manifest`/source-bundle format and verify:

1. evaluator input contains source material only;
2. blind labels are frozen before any Tender Agent artifact is attached;
3. schemas accept valid artifacts and reject invalid/ambiguous states;
4. comparator TP/FP/FN, unsupported claims, contradictions and discovery deltas are sensible;
5. low confidence/source conflict/provenance problems/material disagreements route to `NEEDS_REVIEW`;
6. Product Owner promotion changes review state only.

The canonical real seed set remains the two Cybox procurements and the RSL procurement, but they must be re-grounded from original public source materials. Previous prose reviews are not benchmark truth.

## Local Mac mini boundary

Only the following remains for Codex/local execution:

- acquire the original public-source artifacts for 1–3 calibration procurements through the accepted Tender Agent path;
- compute/normalize document hashes and manifests;
- run the actual local Tender Agent runtime after blind labels are frozen;
- persist the resulting runtime artifacts for comparator execution.

Everything else in this phase should remain GitHub/CI-driven.

## Exit criteria for Phase 1

Phase 1 is complete when repository CI passes and 1–3 real calibration bundles confirm the anti-circularity/schema/comparator/review-state invariants. Only then should #52 proceed to autonomous 30–50-case corpus collection.
