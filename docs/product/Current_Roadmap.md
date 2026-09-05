# Tender Agent — Current Roadmap

Updated: 2026-09-05
Product-code baseline at roadmap pivot: `df7a50192fb5de9a006de7a6ddea06bb8e3e3471`

## 1. Executive status

Tender Agent is past architecture recovery, Commercial MVP packaging, single-case proof-of-capability, the main PILOT-001 analysis hardening cycle, and the first Supplier Engine integration sequence.

Current product capabilities include:

- recovered canonical business registry `M-001..M-055`;
- Commercial MVP v1 and restricted-pilot packages;
- real Mac mini read-only procurement E2E;
- governed ARV-001 quality acceptance;
- PILOT-001 hardening through D04..D09.1;
- Supplier Engine increments `SUPPLIER-ENGINE-001`, `002`, `002.1`, `003`, and `004` merged.

`SUPPLIER-ENGINE-004` now provides a comparison-ready per-position offer read model that can combine public-web offers and formal quotation/TKP inputs while preserving provenance, unknown commercial fields, and a controlled M-021 handoff. Public ranking cannot create a formal supplier recommendation by itself.

The next **real Supplier/TKP/Economics acceptance is temporarily input-blocked** because no real TKP is currently available. This is not an engineering failure and does not justify fabricating acceptance with synthetic TKP data. Synthetic quotations may still be used for regression and edge-case coverage, but not as a substitute for real business evidence.

Therefore the active product phase is now:

**PROCUREMENT INTELLIGENCE QUALITY — SEARCH + DOCUMENTATION**

The highest-value work while waiting for real TKP is to improve and measure the two upstream capabilities every later business stage depends on:

1. finding the right procurements;
2. extracting and analysing their documentation accurately, completely, and with source-grounded evidence.

The product remains operator-assisted and restricted. No autonomous bid submission, EDS/signature, supplier email automation, purchase/order execution, or uncontrolled external action is authorized.

## 2. Current roadmap decision

### Temporarily parked acceptance gate

`REAL SUPPLIER + TKP + ECONOMICS + RISK + GO/NO-GO VALIDATION`

State: `WAITING_FOR_REAL_TKP / INPUT-BLOCKED`.

Resume trigger: at least one real supplier TKP/quotation suitable for a real GOODS procurement becomes available. Prefer several independent real quotations before making broad commercial-quality claims.

While this gate is waiting for external input, engineering capacity moves upstream rather than idling or manufacturing fake acceptance evidence.

### Active P0 phase

`PROCUREMENT INTELLIGENCE QUALITY`

Two parallel P0 branches are now canonical:

- `DISCOVERY-QA-001` — procurement search quality benchmark and relevance hardening (#50);
- `DOCUMENT-QA-001` — source-grounded document analysis quality benchmark (#51).

The operating principle for both is **benchmark first, implementation second**. Baseline quality must be measured on a fixed truth set before search heuristics, extraction logic, prompts, or ranking weights are changed.

## 3. First-wave lifecycle — actual maturity

The first-wave business target remains:

`tender → analysis → supplier-side → economics/risk → owner approval → bid package → manual submission → receipt → outcome`

### Block A — Platform skeleton

Status: **implemented and operationally exercised**.

Deal/status/document/audit foundations, workflow/runtime contours, controlled access, storage/readiness, operator workspace, evidence and report flows are present.

### Block B — Intake & analysis

Status: **most mature; active quality-hardening target**.

Current real 44-FZ path:

`public search → relevance selection → document intake → completeness → evidence-grounded analysis → human report`.

PILOT-001 already hardened:

- evidence binding;
- numeric values and units;
- source-fact recall and retention;
- procurement scope semantics (`GOODS / SERVICES / WORKS / RENTAL / MIXED / UNRESOLVED`);
- downstream semantic consistency;
- RFQ presentation consistency.

The next maturity step is no longer another isolated case fix. It is a reusable quality benchmark that tells us where search and document analysis fail across many real public procurements.

Known source robustness debt remains:

- D05 — incomplete document sets; safe fail-closed behavior is correct, but upstream EIS incompleteness vs intake coverage gap still needs classification;
- D06 — one EIS `unsupported_layout` occurrence; reproduce/classify before parser changes.

### Block C — Supplier Engine

Status: **core integration sequence implemented through SE-004; real business acceptance waiting for real TKP**.

Merged sequence:

#### SUPPLIER-ENGINE-001 — position-level supplier offer matching

- unified procurement-position / supplier-offer contract;
- source attribution;
- deterministic article/model/brand/manufacturer/title matching;
- VAT/MOQ/lead-time normalization without invented defaults;
- conflicting explicit identifiers rejected;
- ranking without autonomous commercial winner selection.

#### SUPPLIER-ENGINE-002 — public offer discovery adapter

- position-aware public web search;
- public result → `SupplierOfferCandidate` conversion;
- source-evidenced price/VAT/MOQ/delivery extraction;
- marketplace filtering and supplier-domain deduplication;
- provider failures propagate without fabricated offers.

#### SUPPLIER-ENGINE-002.1 — RU/EN identifier evidence normalization

- Cyrillic/Latin normalization for identifiers;
- explicit evidence required before an identifier is copied into an offer candidate;
- no fabricated fallback title when search evidence lacks one.

#### SUPPLIER-ENGINE-003 — product-page enrichment

- bounded public product-page fetch;
- private/local/unsafe targets and redirects rejected;
- source-backed price, VAT, MOQ, delivery, availability and identifiers;
- missing commercial fields remain unknown.

#### SUPPLIER-ENGINE-004 — comparison-ready offer set + M-021/TKP handoff

- unified comparison-ready per-position offer read model;
- public-web and formal quotation/TKP adapters with provenance;
- deterministic merge;
- explicit M-021 handoff state;
- public ranking cannot create formal recommendation or selected supplier;
- formal M-021 recommendation remains quotation-backed.

Engineering can still test this contour with public offers and synthetic edge-case quotations, but the **real commercial acceptance gate stays open until genuine TKP input exists**.

### Block D — Finance / risk / approval

Status: **implemented in bounded operator form; real integrated validation waiting for real TKP**.

Existing commercial workspace includes:

- manual TKP registration;
- quote comparison;
- deterministic cost model;
- cash-gap estimate;
- financing strategy;
- finance memo;
- contract risk;
- CEO approval package;
- bid-readiness status.

The required future acceptance cycle remains:

`real supplier offers/TKP → comparison → economics → contract risk → integrated GO/NO-GO → owner decision record`.

### Block E — Bid / submission / outcome

Status: **canonical/recovery coverage exists; external execution remains restricted**.

Bid document collection, package skeleton and completeness/readiness state exist. Final submission remains manual; no ETP mutation/login, EDS/signature, or autonomous submission is open.

## 4. P0 — DISCOVERY-QA-001 (#50)

### Goal

Make procurement search measurably better at surfacing tenders that are actually relevant to the configured supplier/company profile while reducing false positives and preserving explainability.

### Method

Build a versioned benchmark of real public 44-FZ query/candidate cases before changing ranking logic.

Initial corpus target: at least `30–50` labeled query/candidate cases, designed to grow to `50–100+` without changing the evaluation contract.

The corpus should contain:

- clear relevant cases;
- near misses;
- hard negatives with similar titles but wrong procurement subject;
- GOODS / WORKS / SERVICES / RENTAL lookalikes;
- duplicate/versioned notices where applicable;
- status/deadline-incompatible cases where the source provides reliable evidence.

### Minimum metrics

- Precision@5;
- Precision@10;
- Recall@K;
- nDCG@K or a documented equivalent ranking-quality metric;
- top-K false-positive rate;
- missed-relevant rate;
- duplicate rate;
- status/deadline correctness where applicable;
- score-reason/explainability coverage.

### Hardening candidates after baseline

Only measured failure classes should drive changes. Candidate improvements include normalized subject/title/OKPD2/document/profile matching, aliases/transliteration, article/model/brand/manufacturer signals for GOODS, category mismatch penalties, lifecycle/status/deadline filtering, duplicate/version handling, and explicit score breakdown.

LLM reranking is **not** the first move. Consider it only if a stable deterministic benchmark demonstrates a residual gap that deterministic ranking cannot reasonably close, and keep any later LLM path bounded and evidence-grounded.

## 5. P0 — DOCUMENT-QA-001 (#51)

### Goal

Measure and improve how accurately and completely Tender Agent extracts material procurement facts from real public tender documentation while minimizing unsupported material conclusions.

### Method

Build a versioned truth-set corpus from real public 44-FZ document packages across GOODS, SERVICES, WORKS and RENTAL where suitable examples are available.

Expected source-grounded fields should include, where present:

- procurement subject/category/scope;
- positions, quantity and unit;
- article/model/brand/manufacturer;
- GOST/TU/standards and technical requirements;
- delivery/performance place and deadline;
- payment;
- warranty;
- security/guarantee;
- acceptance;
- penalties/liability;
- licenses/SRO/certificates/eligibility;
- required bid documents;
- material contract terms.

Preserve source document plus page/line/fragment reference when the source format allows reliable localization. Never invent source coordinates.

### Minimum metrics

- factual accuracy;
- material-fact recall;
- grounding precision;
- unsupported material claim rate;
- contradiction rate;
- correct abstention rate (`UNKNOWN`, `INSUFFICIENT_EVIDENCE`, or equivalent);
- completeness classification accuracy.

### Error taxonomy

Every miss should be attributable to a pipeline stage rather than labelled simply “bad analysis”:

`source acquisition → completeness → parsing → extraction → scope/category → evidence binding → reasoning → serialization/reporting`.

D05 and D06 are folded into this diagnostic programme without weakening fail-closed behavior.

After deterministic instrumentation is stable, deterministic and local-LLM outputs may be compared on the **same truth set**. The LLM path must not weaken grounding or abstention rules.

## 6. P1 after both P0 branches — integrated Procurement Intelligence acceptance

After DISCOVERY-QA and DOCUMENT-QA have stable baselines, run one integrated evaluation:

`query → ranked top-K → selected procurement → document package → completeness → extracted truth → analysis/report`.

This should attribute quality loss to a precise stage and prevent downstream analysis tuning from hiding upstream search/source problems.

Target result: a repeatable scorecard for the whole pre-supplier intelligence contour.

No real TKP is required for this phase.

## 7. Useful parallel work while real TKP is unavailable

### P1 — public-offer Supplier Engine dry runs

Exercise SE-001..004 on real GOODS procurements using only public offer evidence. This can validate discovery, matching, evidence retention, enrichment and comparison-read-model behavior, but must **not** be presented as real Supplier/TKP commercial acceptance.

### P1 — real-TKP readiness package

Prepare and validate the input template/checklist so the first genuine TKP can be registered immediately when it appears: supplier identity, position mapping, price/currency, VAT, MOQ, delivery, validity, source artifact and unresolved fields.

### P1 — controlled local-LLM multi-case reliability

Single-case local LLM E2E passed historically, while multi-case pilot evidence was fallback-heavy. Measure repeated local completion separately using the DOCUMENT-QA truth set rather than weakening fallback/evidence rules.

### P2 — electrical/domain ontology

Improve aliases, model/article normalization, standards, characteristic names and truth packs. This is unusually high leverage now because it can improve both procurement relevance ranking and technical-document extraction.

### P2 — operator UX / explainability

Improve only evidence-backed operator friction: search score breakdown, why-result-matched, document completeness reason, extracted-fact provenance, missing-data state, and review/audit links.

### P2 — source expansion

223-FZ and private industrial procurement remain planned, but should not dilute the current 44-FZ quality benchmark. Establish the 44-FZ baseline first, then add each source through a separate connector/acceptance contract.

### P2 — repository governance

`main` branch protection / required checks remain a separate engineering-hygiene item and are not the current product P0.

### P3 — historical P8.05 SOAP temporal health

Keep separate from the current public-read-only product path.

## 8. Governance debt

Historical PILOT-001 issue #23 remains formally open/stale while later development proceeded on the assumption that the pilot hardening gate had passed. Reconcile this against the final PO replay evidence, but do not restart product work solely because issue bookkeeping is stale.

## 9. Deferred / not authorized

Do not open yet:

- autonomous bid submission;
- ETP mutation/login automation;
- EDS/signature;
- supplier email automation;
- autonomous ordering/purchase;
- unattended external execution;
- broad agent autonomy;
- self-serve SaaS claims;
- multi-tenant SaaS hardening before repeat-use evidence;
- broad M-049/M-050 runtime expansion;
- promotion of M-052..M-055 to full runtime modules without a separately approved phase.

## 10. Updated critical path

```text
ARV-001 quality freeze ✅
  ↓
Mac mini real E2E ✅
  ↓
PILOT-001 D04..D09.1 hardening ✅
  ↓
Supplier Engine 001..004 ✅
  ↓
REAL TKP ACCEPTANCE — WAITING FOR INPUT
  │
  ├──────── while waiting ────────┐
  ↓                               ↓
DISCOVERY-QA-001 (#50)         DOCUMENT-QA-001 (#51)
  ↓                               ↓
search benchmark + hardening   truth set + analysis hardening
  └──────────────┬────────────────┘
                 ↓
INTEGRATED SEARCH → DOCS → ANALYSIS QUALITY ACCEPTANCE
                 ↓
        when real TKP arrives
                 ↓
REAL SUPPLIER + TKP + ECONOMICS + RISK + GO/NO-GO
                 ↓
CONTROLLED BID PACKAGE + COMPLETENESS
                 ↓
MANUAL SUBMISSION + RECEIPT + OUTCOME AUDIT
                 ↓
FIRST-WAVE BUSINESS LIFECYCLE PROVEN
                 ↓
REPEATED REAL COMMERCIAL PILOTS
                 ↓
SOURCE EXPANSION + PRODUCT HARDENING
                 ↓
ONLY THEN: broader automation / SaaS / external-execution review
```

## 11. Immediate next step

Start with **DISCOVERY-QA-001 benchmark construction and baseline measurement**, in parallel with the DOCUMENT-QA truth-set skeleton.

Do not tune search weights or add new analysis heuristics before the baselines exist. The first deliverable is not “better code”; it is a fixed corpus plus reproducible metrics showing exactly where current quality is weak.

Once the baseline identifies the dominant failure classes, make the smallest targeted hardening increments and rerun the exact same benchmark. This creates measurable quality improvement instead of another case-by-case tuning cycle.

## 12. Roadmap principle

While a downstream gate is blocked only by unavailable real-world input, move engineering effort to the highest-leverage upstream quality work that can be validated independently. Preserve the blocked gate and resume it immediately when genuine evidence becomes available.
