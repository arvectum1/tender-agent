# PILOT-001 — Operational multi-case validation

Status: `READY_FOR_LOCAL_EXECUTION`

## Purpose

Validate the already accepted Mac mini autonomous procurement path across several independent real procurements before calling the read-only Tender Agent workflow operationally ready.

This is a validation task, not a product-feature task. The pilot must reuse the canonical workflow without changing product code between cases:

`public 44-FZ discovery -> deterministic relevance selection -> public document intake -> completeness gate -> local analysis -> HTML report`.

The canonical single-case acceptance remains documented in `docs/operations/MACMINI_AUTONOMOUS_PROCUREMENT_E2E_ACCEPTANCE.md`. PILOT-001 tests whether that accepted path repeats across different procurements.

## Safety and scope boundary

The pilot is read-only with respect to procurement platforms and external counterparties. It must not:

- submit an application or bid;
- authenticate to an ETP;
- send supplier/customer email or RFQ;
- use EDS/digital signature;
- bypass captcha or access controls;
- synthesize missing source documents;
- mutate ARV-001 frozen evidence/governance;
- hot-fix product code between cases.

A blocked or failed case is valid pilot evidence. Record it and continue with the remaining cases unless continuing would risk data loss, external side effects, secrets, or a corrupted runtime.

## Baseline

Pilot branch starts from canonical `main` SHA:

`d68b80a4173ad77594922ae84bad84019031a1a9`

The runtime must use one unchanged source revision for all cases. Record the actual runtime HEAD before case 1 and after the final case. They must match.

Expected local workflow entry point:

```bash
python3 scripts/run_macmini_autonomous_procurement.py \
  --query "<query>" \
  --law 44fz \
  --min-relevance 20
```

Expected success marker:

`MACMINI_AUTONOMOUS_PROCUREMENT_E2E_REPORT_READY`

Expected safe blocked marker:

`MACMINI_AUTONOMOUS_PROCUREMENT_E2E_BLOCKED`

## Case set

Run at least five independent real 44-FZ procurements. Start with these search intents, which deliberately cover adjacent but distinct electrical-goods demand:

1. `электротехническое оборудование`
2. `автоматические выключатели`
3. `кабель силовой`
4. `контакторы`
5. `светильники светодиодные`

Independence rule: every accepted case must have a unique EIS/registry number. If two queries select the same procurement, keep the first result and rerun the colliding slot with the next unused query from this reserve list:

- `шкаф электрический`
- `реле электрическое`
- `источник бесперебойного питания`
- `розетки выключатели`
- `электромонтажные материалы`

Do not alter product code or relevance logic merely to force five successful cases.

## Evidence package

Generated reports, runtime logs, real tender archives and other live-pilot artifacts are local evidence and must not be committed to Git. Store them under the existing ignored `company_agent_runs/` area.

Create one local pilot directory:

`company_agent_runs/PILOT-001-<UTC timestamp>/`

For each attempted case create a subdirectory `case-01` ... `case-N` and preserve:

- raw runner stdout as `runner.json` when machine-readable output is produced;
- generated HTML report, when produced;
- a concise `_evidence.md` record;
- optional sanitized screenshots only when useful for PO review.

Each `_evidence.md` must record:

| Field | Required value |
| --- | --- |
| case | sequential case number |
| query | actual query used |
| registry number | EIS/registry number if selection occurred |
| source URL | public source URL if available |
| run ID | Tender Agent run ID if created |
| result | `REPORT_READY`, `BLOCKED`, or `FAILED_SAFE` |
| final branch | product recommendation such as `GO`, `NO-GO`, `WARN`, or exact backend value; `N/A` if no report |
| attachments | attachment status and downloaded file count |
| analysis | analysis mode; whether local LLM completed; whether deterministic fallback was used |
| report | local report path and HTTP/export status |
| duration | wall-clock execution duration |
| operator intervention | `none` or exact manual action required |
| PO verdict | `PASS`, `PASS_WITH_CORRECTIONS`, `REJECT`, or `PENDING_REVIEW` |
| PO corrections | concise list, `none`, or `pending` |
| defect IDs | links/IDs into pilot defect table |

Do not invent a PO verdict. Until the human-facing report has actually been reviewed, use `PENDING_REVIEW`.

## Defect classification

After all cases have been attempted, build one defect table in the local pilot summary. Do not hot-fix defects during the run.

For every distinct defect record:

- stable defect ID (`PILOT-001-D01`, ...);
- affected case numbers;
- frequency (`affected cases / attempted cases`);
- severity: `P0`, `P1`, `P2`, or `P3`;
- layer: `SOURCE`, `DOCUMENT_INTAKE`, `EXTRACTION`, `ANALYSIS`, `REPORT`, `RUNTIME`, `GOVERNANCE`;
- classification: `SYSTEMATIC`, `PROCUREMENT_SPECIFIC`, or `UNRESOLVED`;
- evidence/reference;
- proposed next action.

Classification guidance:

- `SYSTEMATIC`: repeats in 2+ independent cases or is demonstrably caused by shared runtime/product behavior.
- `PROCUREMENT_SPECIFIC`: caused by the source procurement/document set and not reproduced elsewhere.
- `UNRESOLVED`: evidence is insufficient to distinguish the two.

Any unsafe external side effect, corrupted evidence identity, fabricated source fact, silent LLM/fallback misreporting, or material human-facing conclusion unsupported by source evidence is `P0` regardless of frequency.

## Pilot completion criteria

PILOT-001 is complete when all are true:

1. At least five unique real procurements have been attempted through the unchanged canonical E2E workflow.
2. Every attempted case has a canonical local evidence record.
3. Every generated report has an explicit PO verdict; blocked cases have an explicit operational disposition.
4. A consolidated defect table includes frequency and severity.
5. Systematic defects are separated from procurement-specific edge cases or explicitly marked unresolved.
6. Runtime source HEAD is unchanged across the pilot.
7. A final decision is recorded as exactly one of:
   - `OPERATIONALLY_READY_FOR_RESTRICTED_READ_ONLY_PILOT`;
   - `NOT_READY_SINGLE_P0_CLOSURE_BRANCH_REQUIRED`.

## Final decision rule

Use `NOT_READY_SINGLE_P0_CLOSURE_BRANCH_REQUIRED` if any of the following is true:

- any open `P0` defect exists;
- fewer than five unique real procurements were actually exercised;
- the runtime revision changed between cases;
- any generated report remains `PO REJECTED` for a systematic reason;
- evidence is insufficient to distinguish a potentially systematic material defect from an incidental case issue.

Otherwise, if all five or more cases have complete evidence, no open P0 remains, and human review shows the reports are decision-useful within the restricted read-only boundary, record `OPERATIONALLY_READY_FOR_RESTRICTED_READ_ONLY_PILOT`.

This decision does not authorize autonomous bid submission, ETP mutation, supplier messaging, EDS use, or a mass external pilot.

## Final local summary template

Create `PILOT-001-SUMMARY.md` in the local pilot directory with:

```markdown
# PILOT-001 summary

Runtime HEAD before: <sha>
Runtime HEAD after: <sha>
Cases attempted: <n>
Unique registry numbers: <n>
Report-ready: <n>
Blocked/failed-safe: <n>
PO PASS: <n>
PO PASS_WITH_CORRECTIONS: <n>
PO REJECT: <n>

## Case matrix
<one row per case>

## Defect table
<frequency/severity/classification table>

## Systematic findings
<findings or none>

## Procurement-specific findings
<findings or none>

## Final decision
<exact allowed decision token>

## Next P0 branch, if required
<single systemic closure branch scope, or none>
```
