# PILOT-001 — Operational multi-case validation

Status: `BLOCKED_PRECONDITION_RUNTIME_STALE`

## Purpose

Validate the accepted Mac mini autonomous procurement path across several independent real procurements before calling the read-only Tender Agent workflow operationally ready.

This is a validation task, not a product-feature task. Reuse the canonical workflow without changing product code between cases:

`public 44-FZ discovery -> deterministic relevance selection -> public document intake -> completeness gate -> local analysis -> HTML report`.

## Safety boundary

The pilot remains read-only with respect to procurement platforms and counterparties. It must not submit bids, authenticate to an ETP, send supplier/customer messages, use EDS, bypass captcha/access controls, synthesize missing source documents, mutate ARV-001 frozen evidence/governance, or hot-fix product code between cases.

A blocked or failed case is valid evidence. Record it and continue unless continuing would risk data loss, external side effects, secrets, or runtime corruption.

## Mandatory preflight

Before case 1, the runtime checkout must be reconciled with canonical GitHub `main`.

Record:

- `git rev-parse HEAD`;
- `git rev-parse origin/main` after `git fetch origin`;
- `git status --short`;
- whether `scripts/run_macmini_autonomous_procurement.py` exists.

Pilot execution MUST NOT start when the runtime HEAD is stale relative to `origin/main` or the accepted runner is absent.

The first attempted execution on 2026-09-01 did not constitute a valid multi-case pilot: runtime HEAD `84f859ca4998b58fd689dabc2221c88fef3a9420` is an ancestor of canonical `main` by 204 commits, and `scripts/run_macmini_autonomous_procurement.py` was added later in that history. Therefore the observed block is classified as `RUNTIME_PRECONDITION_STALE_CHECKOUT`, not as evidence about EIS transport, procurement selection, document intake, analysis quality, fallback behavior, or report quality.

After a clean fast-forward reconciliation, record the new runtime HEAD as `RUNTIME_HEAD_BEFORE` and keep it unchanged for all pilot cases.

## Runner

Expected entry point:

```bash
python3 scripts/run_macmini_autonomous_procurement.py \
  --query "<query>" \
  --law 44fz \
  --min-relevance 20
```

Success marker:

`MACMINI_AUTONOMOUS_PROCUREMENT_E2E_REPORT_READY`

Safe blocked marker:

`MACMINI_AUTONOMOUS_PROCUREMENT_E2E_BLOCKED`

## Case set

Exercise at least five UNIQUE real 44-FZ procurements.

Initial search intents:

1. `электротехническое оборудование`
2. `автоматические выключатели`
3. `кабель силовой`
4. `контакторы`
5. `светильники светодиодные`

Reserve queries for duplicate selections or non-actionable searches:

- `шкаф электрический`
- `реле электрическое`
- `источник бесперебойного питания`
- `розетки выключатели`
- `электромонтажные материалы`

Every counted case must have a unique registry/EIS number. Do not change relevance logic or thresholds merely to force five successful cases.

## Evidence package

Live pilot artifacts stay local under ignored `company_agent_runs/` and must not be committed.

Use:

`company_agent_runs/PILOT-001-<UTC timestamp>/`

For every attempted case preserve:

- raw runner output as `runner.json` when machine-readable output exists;
- generated HTML report when produced;
- `case-NN/_evidence.md`.

Each evidence record must include case, query, registry number, source URL, run ID, result (`REPORT_READY`, `BLOCKED`, `FAILED_SAFE`), final recommendation, attachment status/count, analysis mode, whether local LLM completed, whether fallback was used, report path/status, duration, operator intervention, PO verdict, PO corrections, and defect IDs.

Do not invent PO review. Until the human-facing report is actually reviewed, use `PENDING_REVIEW`.

## Defect classification

After all cases, build one defect table with:

- stable ID (`PILOT-001-D01`, ...);
- affected cases;
- frequency;
- severity (`P0`/`P1`/`P2`/`P3`);
- layer (`SOURCE`, `DOCUMENT_INTAKE`, `EXTRACTION`, `ANALYSIS`, `REPORT`, `RUNTIME`, `GOVERNANCE`);
- classification (`SYSTEMATIC`, `PROCUREMENT_SPECIFIC`, `UNRESOLVED`);
- evidence;
- proposed next action.

`SYSTEMATIC` means repeated in 2+ independent cases or demonstrably caused by shared product/runtime behavior. `PROCUREMENT_SPECIFIC` means caused by a particular source/document set and not reproduced elsewhere. Otherwise use `UNRESOLVED`.

Any unsafe external side effect, corrupted evidence identity, fabricated source fact, silent LLM/fallback misreporting, or material human-facing conclusion unsupported by source evidence is `P0` regardless of frequency.

## Completion criteria

PILOT-001 is complete only when all are true:

1. At least five unique real procurements were exercised through the unchanged canonical E2E workflow.
2. Every attempt has a local evidence record.
3. Every generated report has an explicit PO verdict; blocked cases have an explicit operational disposition.
4. A consolidated defect table records frequency and severity.
5. Systematic defects are separated from procurement-specific edge cases or explicitly unresolved.
6. `RUNTIME_HEAD_BEFORE == RUNTIME_HEAD_AFTER` across the actual multi-case run.
7. A final decision is recorded as exactly one of:
   - `OPERATIONALLY_READY_FOR_RESTRICTED_READ_ONLY_PILOT`;
   - `NOT_READY_SINGLE_P0_CLOSURE_BRANCH_REQUIRED`.

Use `NOT_READY_SINGLE_P0_CLOSURE_BRANCH_REQUIRED` if any open P0 exists, fewer than five unique procurements were exercised, runtime source changed between cases, any generated report remains PO-rejected for a systematic reason, or evidence cannot rule out a potentially systematic material defect.

Otherwise, after human review confirms decision-useful reports within the restricted read-only boundary, use `OPERATIONALLY_READY_FOR_RESTRICTED_READ_ONLY_PILOT`.

Neither outcome authorizes autonomous bid submission, ETP mutation, supplier messaging, EDS use, or a mass external pilot.
