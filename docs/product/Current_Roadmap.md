# Tender Agent — Current Roadmap

Updated: 2026-09-05
Baseline product HEAD before this roadmap update: `fe7c3c5384a2fb6ad362a68a43ede23f1f885dd5`

## 1. Executive status

Tender Agent has moved beyond architecture recovery and single-case proof-of-capability.

The repository now contains the recovered canonical business registry, Commercial MVP v1, restricted pilot packaging, a real Mac mini read-only E2E flow, governed ARV-001 quality acceptance, and repeated PILOT-001 hardening across evidence grounding, source-fact recall, procurement-scope semantics, operator output consistency, and RFQ presentation.

The product is **not** yet an autonomous procurement platform. The current operating boundary remains operator-assisted and read-only with respect to procurement participation: no autonomous bid submission, no EDS/signature workflow, no supplier email automation, and no uncontrolled external execution.

The immediate critical path is no longer feature development. It is the **final post-merge Product Owner replay of PILOT-001 after D09.1**, followed by governed closure of PILOT-001 if the replay passes.

## 2. Where we are now

### Governed quality and runtime milestones

- ARV-001 governed quality acceptance: `CLOSED / FROZEN`.
- Decision-useful human-facing report baseline: accepted.
- Mac mini autonomous procurement discovery → analysis → HTML report: accepted single-case E2E.
- Reproducible dependency lock: implemented.
- PILOT-001 multi-case validation: executed; the historical batch exposed systematic analysis defects that triggered D04..D09.1 hardening.
- D01 runtime staleness: closed.
- D02 Basic Auth runtime boundary: closed.
- D03 external storage/readiness: closed.
- D04 grounded deterministic fallback: implemented and iteratively strengthened through D04.2..D04.6.
- D08 source-first GOODS extraction and material source-fact retention: implemented.
- D07 evidence-based procurement scope semantics: implemented.
- D07.1 semantic scope preservation through serialization: implemented.
- D09 scope-consistent operator output: implemented.
- D09.1 scope-consistent RFQ draft for RENTAL/MIXED/UNRESOLVED: implemented and merged.

### Current gate

`FINAL POST-MERGE PILOT-001 PO REPLAY`

The replay must verify the repaired RENTAL case and GOODS controls on the latest accepted runtime without reopening extraction/evidence contracts.

If PASS:

1. record final Product Owner decision;
2. reconcile the stale body of issue #23 with the actual D04..D09.1 history;
3. close PILOT-001;
4. move the critical path from analysis stabilization to full pre-bid decision-cycle operationalization.

If FAIL:

- classify the exact new defect from the replay;
- open only the smallest closure branch necessary;
- do not broaden scope speculatively.

## 3. Canonical architecture coverage

The locked registry is `M-001..M-055`.

Repository governance currently records:

- canonical exact implementation: `M-001..M-048` and `M-051`;
- bounded internal metadata/control implementation: `M-049`, `M-050`;
- reconciled late slots that are explicitly not full runtime modules:
  - `M-052` Notification Layer — `PLATFORM_ONLY`;
  - `M-053` Red Flag Registry — `GOVERNANCE_ONLY`;
  - `M-054` Master Dashboard — `PLATFORM_ONLY`;
  - `M-055` SaaS Productization Tracker — `GOVERNANCE_ONLY`.

This means the next phase should **not** rebuild Supplier, Finance/Risk, or Bid modules from zero. The next job is to operationalize and validate the existing canonical capabilities in real tender cycles.

## 4. First-wave business lifecycle — status by block

### Block A — Platform skeleton

Target modules: M-001, M-002, M-003, M-004, M-051, plus integration/notification support.

Status: **implemented / operationally exercised**.

Evidence includes canonical deal/status/document/audit foundations, workflow/runtime contours, controlled operator console/workspaces, access boundary, storage readiness, audit/evidence flows, and Mac mini runtime execution.

Remaining work is hardening and governance, not greenfield construction.

### Block B — Intake & analysis

Target: tender intake, document ingestion, screening, scoring, summary, compliance/requirements, early risk.

Status: **strongest and most heavily validated product block**.

The current real 44-FZ flow covers:

`public search → relevance selection → documents → completeness → deterministic/LLM analysis → evidence-grounded human report`.

PILOT-001 hardening has materially improved:

- evidence binding;
- numeric value + unit semantics;
- source-fact recall;
- procurement type/scope classification;
- downstream semantic consistency;
- RFQ presentation consistency.

Current unresolved robustness items remain separate:

- D05 incomplete document sets — safe fail-closed behavior is correct, root cause / source completeness deserves later investigation;
- D06 EIS `unsupported_layout` — one unresolved source-layout occurrence, currently non-systematic.

### Block C — Supplier engine

Target modules: M-006, M-016..M-021.

Repository status: **canonical implementation exists**.

Product status: **partially operationalized in commercial/pilot workflows, but not yet proven as a repeated real supplier-side cycle**.

Already present in product contours:

- supplier profile relevance;
- RFQ-first operator workflow;
- RFQ draft generation;
- manual supplier/TKP registration;
- quote normalization/comparison;
- supplier-side artifacts inside the commercial workspace.

Still intentionally manual/closed:

- supplier outbound communication;
- autonomous RFQ sending;
- unattended supplier negotiation.

Next business-value validation should use real supplier/TKP inputs while keeping outbound actions manual.

### Block D — Finance / risk / approval

Target modules: M-022..M-028.

Repository status: **canonical implementation exists**.

Product status: **available in bounded commercial/operator form, not yet accepted as a repeated real end-to-end decision cycle**.

Already present:

- deterministic economics/TKP workspace;
- calibrated contract risk;
- bid-readiness recommendation;
- manual review and operator decision boundary.

Next validation must prove that real supplier quotes can flow through:

`supplier offers → economics → contract risk → integrated recommendation → formal GO / NO-GO decision`.

### Block E — Bid / submission / outcome

Target first-wave path: required docs → package → completeness → submission record → post-submission → outcome.

Repository status: **canonical/recovery coverage exists**.

Product operating status: **not opened as autonomous external execution**.

Current restrictions remain correct:

- final submission manual;
- no ETP mutation/login automation;
- no EDS/signature automation;
- no autonomous procurement participation.

The next useful step after Supplier/Finance validation is a controlled bid-preparation cycle that produces a complete application package and manual-submission receipt/audit trail without yet automating submission.

## 5. Product maturity layers

### Completed

- architecture recovery and registry reconciliation;
- Commercial MVP v1 repository package;
- controlled commercial pilot package;
- design-partner pilot package;
- restricted paid pilot operations setup;
- partner tender folder runner;
- Tender Operator RFQ-first refinement;
- access boundary / workspace / redaction / export / feedback loop;
- ARV-001 quality acceptance;
- real Mac mini E2E;
- PILOT-001 analysis hardening through D09.1.

### Current

- final PILOT-001 post-merge PO replay and closure.

### Next product stage

**Operationalize the full pre-bid decision cycle on real tenders.**

Recommended scope:

1. real procurement intake;
2. real supplier shortlist / manually controlled RFQ;
3. real TKP registration;
4. quote comparison;
5. economics and cash-gap inputs;
6. contract risk;
7. integrated GO / NO-GO memo;
8. owner decision record;
9. complete audit trail.

The goal is to prove not just “the analyzer writes a correct report”, but “the system supports a real commercial decision from tender discovery through supplier economics”.

### Following stage

Controlled bid-package preparation:

- required document checklist;
- collected-document register;
- completeness gate;
- package build;
- manual submission;
- proof-of-submission record;
- outcome tracking.

This would complete the first-wave business lifecycle without opening unsafe autonomy.

## 6. Parallel workstreams

### P0 — PILOT-001 closure

Final post-merge PO replay on latest main, then close issue #23 if PASS.

### P1 — Real supplier/economics decision cycle

Use existing Supplier + TKP + Economics + Contract Risk capabilities on real GOODS procurements. Keep outbound actions manual.

### P1 — Controlled LLM runtime reliability

Single-case local LLM E2E has passed, but the historical multi-case pilot produced fallback-heavy evidence. Separately validate that local LLM completion is repeatable without weakening deterministic fallback or source grounding.

### P1 — Commercial/legal pilot readiness

Maintain restricted pilot rules, local data handling, acceptance criteria, feedback capture, and human-control boundaries before any broader external motion.

### P2 — D05 document completeness

Determine whether incomplete document sets are upstream EIS limitations or an intake coverage gap. Preserve fail-closed behavior.

### P2 — D06 source-layout robustness

Reproduce/classify the `unsupported_layout` case before changing parsing logic.

### P2 — Source expansion

After the current 44-FZ contour is stable, expand toward additional procurement sources. Treat 223-FZ and private industrial procurement connectors as separate source contracts rather than contaminating the accepted 44-FZ path.

### P2 — Domain ontology / electrical vertical

Continue exact product characteristics, standards, normalization, synonymy, and truth-pack work. This should improve relevance and analysis quality without becoming a prerequisite for every procurement type.

### P2 — Operator UX / observability

Prioritize only evidence-driven improvements: run queue, failure reason, report/review state, audit links, workload/cadence visibility.

### P2 — Repository governance

`main` branch protection / required checks are still not enforced at repository level. Add this as engineering hygiene after the current replay gate unless repository administration constraints prevent it.

### P2 — Arvectum OS integration

Continue integration as a consumer/orchestrator of Tender Agent product contracts. Do not make Arvectum OS a prerequisite for Tender Agent operational validation.

### P3 — Historical P8.05 / EIS SOAP temporal health

Keep issue #1 separate from the product critical path. Do not reinterpret a new public EIS flow as an automatic PASS of the historical strict temporal gate.

## 7. Deferred / not authorized

Do not open yet:

- autonomous bid submission;
- ETP login/mutation automation;
- EDS/signature;
- supplier email automation;
- unattended external execution;
- broad agent autonomy;
- self-serve SaaS claims;
- multi-tenant SaaS hardening before real repeat-use evidence;
- broad runtime expansion of M-049/M-050;
- promotion of M-052..M-055 to full runtime modules without a separate approved phase.

## 8. Critical path from here

```text
D09.1 merged
  ↓
FINAL PILOT-001 PO REPLAY
  ↓ PASS
PILOT-001 CLOSED
  ↓
REAL SUPPLIER + TKP + ECONOMICS + RISK + GO/NO-GO CYCLE
  ↓
CONTROLLED BID PACKAGE + COMPLETENESS
  ↓
MANUAL SUBMISSION + RECEIPT + OUTCOME AUDIT
  ↓
FIRST-WAVE BUSINESS LIFECYCLE PROVEN
  ↓
REPEATED REAL PILOTS / COMMERCIAL EVIDENCE
  ↓
SOURCE EXPANSION + PRODUCT HARDENING
  ↓
ONLY THEN: broader automation / SaaS / external execution review
```

## 9. Immediate next step

Run the final post-merge PILOT-001 PO replay on latest `main` with:

- repaired RENTAL Case 03;
- GOODS control cases 04/05/06/08;
- no new product-code changes during replay;
- explicit confirmation that scope/category, next actions, recommendation semantics, RFQ sections, D08 source facts, and evidence provenance remain mutually consistent.

If PASS, close PILOT-001 and immediately open the next operational milestone around **real Supplier/TKP/Economics/Risk/GO-NO-GO validation**, using existing canonical modules rather than rebuilding them.

## 10. Roadmap principle

From this point forward, roadmap priority is determined by **operational evidence and business-cycle completion**, not by the count of implemented modules.

The repository already contains broad canonical coverage. The remaining strategic job is to turn that coverage into a proven, repeatable, auditable tender-business workflow under controlled human boundaries.
