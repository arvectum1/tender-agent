# PILOT-001-D04.4 — GOODS scope selection + safe handoff timeout

## Trigger

Fresh D04.3 runtime re-acceptance on canonical `main` (`7b84f25b9111f72f49046b62ca168b3c07db53cf`) proved the D04.2/D04.3 evidence contract on a real GOODS procurement, but exposed two orchestration defects:

1. GOODS-oriented search queries could hand off SERVICES, WORKS, or mixed procurements because the generic autonomous runner ranked only by relevance and registry uniqueness.
2. A raw stdlib/socket timeout during handoff could escape as an uncaught traceback instead of a structured fail-closed result.

The runtime batch also showed that copying a recent `selection-history.json` is not sufficient to recover registry numbers that older acceptance runs supplied only as explicit CLI exclusions. Fresh acceptance must therefore preserve a cumulative exclusion set across pilot batches.

## Scope

Add a GOODS-scoped pilot runner that composes the existing generic runner and keeps its mixed-category behavior backward compatible.

The GOODS runner must:

- conservatively prefilter search cards whose titles are explicitly SERVICES/WORKS;
- treat canonical `runtime_analysis.procurement_category` as authoritative;
- never surface a non-GOODS terminal run as GOODS success;
- reserve runtime-rejected registries through the existing selection-history mechanism and automatically try the next unique candidate;
- convert raw `TimeoutError` / `socket.timeout` from backend/report calls into structured `E2EBlocked(code="backend_timeout")` output;
- preserve all no-submission/no-email/no-signature/no-ETP safety boundaries.

## Acceptance

Repository tests must prove:

- obvious service/work cards are skipped before handoff;
- ambiguous cards are rejected after canonical runtime classification and the next unique GOODS candidate is selected;
- rejected registries remain in selection history;
- raw timeout becomes structured `backend_timeout`;
- CLI timeout output contains no traceback.

Fresh Mac mini runtime acceptance after merge must use the GOODS-scoped runner and a cumulative explicit exclusion set covering all previously consumed registry numbers.
