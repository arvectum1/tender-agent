# PILOT-001 — Operational multi-case validation

Status: `BLOCKED_PRECONDITION_RUNTIME_STALE`

## Purpose
Validate the accepted Mac mini autonomous procurement path across several independent real procurements before calling the read-only Tender Agent workflow operationally ready.

## Mandatory preflight
The first attempted execution on 2026-09-01 did not constitute a valid multi-case pilot: runtime HEAD `84f859ca4998b58fd689dabc2221c88fef3a9420` is an ancestor of canonical `main`, and `scripts/run_macmini_autonomous_procurement.py` was added later. Reconcile the clean runtime checkout by fast-forwarding to `origin/main`, verify the runner exists, then record that reconciled SHA as `RUNTIME_HEAD_BEFORE` and keep it unchanged across the actual pilot.

This block is `RUNTIME_PRECONDITION_STALE_CHECKOUT`; it is not evidence about EIS transport, procurement selection, document intake, analysis/fallback quality, or report quality.

## Safety boundary
Read-only only: no bid submission, ETP mutation/login, supplier/customer messages, EDS, captcha bypass, source fabrication, ARV-001 evidence mutation, or product hot-fixes between cases.

## Runner
```bash
python3 scripts/run_macmini_autonomous_procurement.py \
  --query "<query>" \
  --law 44fz \
  --min-relevance 20
```

Success: `MACMINI_AUTONOMOUS_PROCUREMENT_E2E_REPORT_READY`  
Safe block: `MACMINI_AUTONOMOUS_PROCUREMENT_E2E_BLOCKED`

## Case set
Exercise at least five UNIQUE real 44-FZ procurements. Initial queries:
1. `электротехническое оборудование`
2. `автоматические выключатели`
3. `кабель силовой`
4. `контакторы`
5. `светильники светодиодные`

Reserve queries: `шкаф электрический`, `реле электрическое`, `источник бесперебойного питания`, `розетки выключатели`, `электромонтажные материалы`.

Every counted case must have a unique registry/EIS number. Do not change relevance logic or thresholds to force results.

## Evidence
Keep live artifacts local under ignored `company_agent_runs/PILOT-001-<UTC timestamp>/`. For each attempt preserve runner output, HTML report if produced, and `_evidence.md` containing query, registry, source URL, run ID, result, recommendation, document status/count, analysis mode, local-LLM/fallback evidence, report status/path, duration, intervention, PO verdict/corrections, and defect IDs. Until actual human review, PO verdict is `PENDING_REVIEW`.

## Defects
Record stable ID, affected cases, frequency, severity P0-P3, layer, classification (`SYSTEMATIC`, `PROCUREMENT_SPECIFIC`, `UNRESOLVED`), evidence, and next action. Unsafe external side effect, corrupted evidence identity, fabricated source fact, silent LLM/fallback misreporting, or material unsupported human-facing conclusion is P0.

## Completion
PILOT-001 is complete only after 5+ unique real procurements are exercised on one unchanged reconciled runtime SHA, every attempt has evidence, reports have PO verdicts, and defects are consolidated/classified.

Final decision must be exactly one of:
- `OPERATIONALLY_READY_FOR_RESTRICTED_READ_ONLY_PILOT`
- `NOT_READY_SINGLE_P0_CLOSURE_BRANCH_REQUIRED`

Neither outcome authorizes autonomous bid submission, ETP mutation, supplier messaging, EDS use, or a mass external pilot.
