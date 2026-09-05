# Tender Agent — Current Roadmap

Updated: 2026-09-05
Product-code baseline at Procurement Intelligence pivot: `df7a50192fb5de9a006de7a6ddea06bb8e3e3471`

## 1. Executive status

Tender Agent is past architecture recovery, Commercial MVP packaging, single-case proof-of-capability, the main PILOT-001 analysis hardening cycle, and the first Supplier Engine integration sequence.

Current product capabilities include:

- recovered canonical business registry `M-001..M-055`;
- Commercial MVP v1 and restricted-pilot packages;
- real Mac mini read-only procurement E2E;
- governed ARV-001 quality acceptance;
- PILOT-001 hardening through D04..D09.1;
- Supplier Engine increments `SUPPLIER-ENGINE-001`, `002`, `002.1`, `003`, and `004` merged.

`SUPPLIER-ENGINE-004` provides a comparison-ready per-position offer read model that can combine public-web offers and formal quotation/TKP inputs while preserving provenance, unknown commercial fields, and a controlled M-021 handoff. Public ranking cannot create a formal supplier recommendation by itself.

The next **real Supplier/TKP/Economics acceptance is temporarily input-blocked** because no genuine TKP is currently available. This is not an engineering failure and does not justify fabricating acceptance with synthetic TKP data. Synthetic quotations remain acceptable for regression/edge-case tests only.

Therefore the active product phase is:

**PROCUREMENT INTELLIGENCE QUALITY — SEARCH + DOCUMENTATION**

The immediate objective is to improve and measure two upstream capabilities on real public 44-FZ procurements:

1. finding the right procurements;
2. extracting and analysing their documentation accurately, completely, and with source-grounded evidence.

The Product Owner is **not** expected to manually label 30–50 procurements. Benchmark creation is now designed as an AI-assisted, independently evaluated pipeline with final Product-Owner verification.

The product remains operator-assisted and restricted. No autonomous bid submission, EDS/signature, supplier email automation, purchase/order execution, or uncontrolled external action is authorized.

## 2. Current roadmap decision

### Temporarily parked acceptance gate

`REAL SUPPLIER + TKP + ECONOMICS + RISK + GO/NO-GO VALIDATION`

State: `WAITING_FOR_REAL_TKP / INPUT-BLOCKED`.

Resume trigger: at least one real supplier TKP/quotation suitable for a real GOODS procurement becomes available. Prefer several independent real quotations before broad commercial-quality claims.

### Active P0 programme

`PROCUREMENT INTELLIGENCE QUALITY`

Canonical tasks:

- `BENCHMARK-PIPELINE-001` — autonomous corpus collection, blind AI labeling and human verification (#52);
- `DISCOVERY-QA-001` — procurement search quality benchmark and relevance hardening (#50);
- `DOCUMENT-QA-001` — source-grounded document analysis quality benchmark (#51).

The operating principle is **benchmark first, implementation second**. Baseline quality must be measured on a fixed corpus before search weights, extraction logic, prompts, ranking rules, or report heuristics are changed.

## 3. Benchmark governance — canonical model

### 3.1 Why this model

The benchmark should scale to `30–50` cases initially and `50–100+` later without requiring the Product Owner to perform repetitive manual extraction and labeling.

The benchmark therefore uses three review states:

- `AI_CURATED_SILVER` — independently AI-labeled, source-grounded, structurally valid, not yet individually Product-Owner verified;
- `NEEDS_REVIEW` — material uncertainty, source conflict, weak provenance, schema failure, or material evaluator/system disagreement;
- `HUMAN_VERIFIED_GOLD` — case/fields explicitly reviewed and approved by the Product Owner.

An AI-generated label must never be described as human gold without explicit Product-Owner verification.

The **final benchmark release and scorecard** must be reviewed and explicitly verified by the Product Owner before it becomes the accepted quality baseline. This final verification does not require the Product Owner to manually reconstruct every case from scratch.

### 3.2 Anti-circularity / blind evaluation

The system under test must not influence the independent first-pass label.

Required per-case order:

`public source bundle -> blind independent evaluator label -> freeze label -> Tender Agent output -> automatic comparator -> review routing`

The independent evaluator must not see Tender Agent ranking, extracted facts, report text, or score reasons before its first-pass label is frozen.

### 3.3 Roles

#### Tender Agent

- discovers real public procurements;
- collects accepted public-source metadata/document bundles;
- produces normal search and analysis outputs;
- remains the system under test.

#### Local runner / Codex

Codex is used only for work that must run on the local machine:

- run/update local Tender Agent runtime;
- collect/download public procurement artifacts through the accepted product path;
- create bundle manifests/hashes;
- prepare evaluator input bundles;
- execute benchmark/comparator commands;
- persist local outputs/reports.

Codex/local runner is not the semantic source of truth.

#### Independent evaluator (ChatGPT)

- reviews the source bundle independently;
- labels procurement relevance;
- extracts source-grounded document truth under a strict schema;
- uses `UNKNOWN` / `INSUFFICIENT_EVIDENCE` rather than guessing;
- preserves source references where technically reliable;
- exposes confidence and uncertainty.

#### Product Owner

- reviews the final benchmark/release and scorecard;
- verifies/rejects benchmark conclusions;
- reviews disputed/material cases where needed;
- may promote reviewed cases/fields to `HUMAN_VERIFIED_GOLD`.

### 3.4 Calibration cases

The three procurements previously reviewed with the Product Owner — two Cybox cases and the RSL procurement — are the preferred initial calibration set **once their original public source materials are imported into the same benchmark bundle/schema**.

Prior prose reviews are calibration context only. Their truth labels must be regenerated from the source bundles under the new blind-evaluation contract.

## 4. First-wave lifecycle — actual maturity

The first-wave business target remains:

`tender -> analysis -> supplier-side -> economics/risk -> owner approval -> bid package -> manual submission -> receipt -> outcome`

### Block A — Platform skeleton

Status: **implemented and operationally exercised**.

Deal/status/document/audit foundations, workflow/runtime contours, controlled access, storage/readiness, operator workspace, evidence and report flows are present.

### Block B — Intake & analysis

Status: **most mature; active quality-hardening target**.

Current real 44-FZ path:

`public search -> relevance selection -> document intake -> completeness -> evidence-grounded analysis -> human report`.

PILOT-001 already hardened evidence binding, numeric values/units, source-fact recall/retention, procurement scope semantics, downstream semantic consistency and RFQ presentation consistency.

The next maturity step is a reusable benchmark across many real procurements rather than another isolated case-by-case fix.

Known source robustness debt remains:

- D05 — incomplete document sets; safe fail-closed behavior is correct, but upstream EIS incompleteness vs intake coverage gap still needs classification;
- D06 — one EIS `unsupported_layout` occurrence; reproduce/classify before parser changes.

### Block C — Supplier Engine

Status: **core integration sequence implemented through SE-004; real business acceptance waiting for genuine TKP**.

Merged sequence:

- `SUPPLIER-ENGINE-001` — position-level supplier offer matching;
- `SUPPLIER-ENGINE-002` — public offer discovery adapter;
- `SUPPLIER-ENGINE-002.1` — RU/EN identifier evidence normalization;
- `SUPPLIER-ENGINE-003` — bounded product-page enrichment;
- `SUPPLIER-ENGINE-004` — comparison-ready offer set + M-021/TKP handoff.

Engineering may still exercise this contour with public offers and synthetic edge-case quotations, but the **real commercial acceptance gate remains open until genuine TKP input exists**.

### Block D — Finance / risk / approval

Status: **implemented in bounded operator form; real integrated validation waiting for real TKP**.

Existing commercial workspace includes manual TKP registration, quote comparison, deterministic cost model, cash-gap estimate, financing strategy, finance memo, contract risk, CEO approval package and bid-readiness state.

Required future acceptance:

`real supplier offers/TKP -> comparison -> economics -> contract risk -> integrated GO/NO-GO -> owner decision record`.

### Block E — Bid / submission / outcome

Status: **canonical/recovery coverage exists; external execution remains restricted**.

Bid document collection, package skeleton and completeness/readiness state exist. Final submission remains manual; no ETP mutation/login, EDS/signature, or autonomous submission is open.

## 5. P0 — BENCHMARK-PIPELINE-001 (#52)

### Goal

Build the shared, batchable benchmark infrastructure used by both search and document QA so that a 30–50 case corpus can be collected and independently labeled with minimal Product-Owner manual work.

### Required artifacts

At minimum version:

1. `case_manifest` — procurement identity, source URLs, acquisition timestamp, document hashes, source scope;
2. `blind_discovery_label` — `RELEVANT | PARTIALLY_RELEVANT | IRRELEVANT | UNCLEAR`, reason/evidence/confidence;
3. `blind_document_truth` — structured material facts with evidence/confidence/abstention;
4. `tender_agent_output_ref` — tested runtime/version and output refs;
5. `comparison_result` — TP/FP/FN, unsupported claims, contradictions, misses and ranking deltas;
6. `review_state` — `AI_CURATED_SILVER | NEEDS_REVIEW | HUMAN_VERIFIED_GOLD` plus reviewer metadata;
7. aggregate scorecard.

### Acceptance

- blind-label-before-system-output is enforced by workflow/tests, not only documentation;
- Tender Agent output cannot leak into first-pass evaluator bundles;
- corpus collection/comparison is batchable without Product-Owner per-case orchestration;
- uncertainty/review routing is explicit;
- final benchmark release can be verified by the Product Owner without rewriting all labels manually;
- calibration cases use the same pipeline as future cases.

## 6. P0 — DISCOVERY-QA-001 (#50)

### Goal

Make procurement search measurably better at surfacing tenders relevant to the configured supplier/company profile while reducing false positives and preserving explainability.

### Corpus

Use #52 to collect at least `30–50` real public 44-FZ query/candidate cases, designed to grow to `50–100+`.

Include clear relevant cases, near misses, hard negatives, GOODS/WORKS/SERVICES/RENTAL lookalikes, duplicates/versioned notices, and lifecycle/deadline mismatches where source evidence permits.

### Minimum metrics

- Precision@5;
- Precision@10;
- Recall@K;
- nDCG@K or documented equivalent;
- top-K false-positive rate;
- missed-relevant rate;
- duplicate rate;
- status/deadline correctness where applicable;
- score-reason/explainability coverage.

### Hardening policy

Only measured failure classes drive changes. Candidate areas include normalized subject/title/OKPD2/document/profile matching, aliases/transliteration, article/model/brand/manufacturer signals for GOODS, category mismatch penalties, lifecycle/status/deadline filtering, duplicate/version handling and explicit score breakdown.

LLM reranking is not the first move. Consider it only after a stable deterministic benchmark demonstrates a residual gap.

## 7. P0 — DOCUMENT-QA-001 (#51)

### Goal

Measure and improve how accurately and completely Tender Agent extracts material facts from real public tender documentation while minimizing unsupported material conclusions.

### Truth fields

Where present in sources, capture:

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
- bid-document requirements;
- material contract terms.

Preserve source document plus page/line/fragment reference where reliable. Never invent source coordinates.

### Minimum metrics

- factual accuracy;
- material-fact recall;
- grounding precision;
- unsupported material claim rate;
- contradiction rate;
- correct abstention rate;
- completeness classification accuracy.

### Error taxonomy

`source acquisition -> completeness -> parsing -> extraction -> scope/category -> evidence binding -> reasoning -> serialization/reporting`

D05 and D06 are folded into this diagnostic programme without weakening fail-closed behavior.

Deterministic and local-LLM analysis may later be compared on the **same frozen truth set**. The LLM path must not weaken grounding or abstention rules.

## 8. P1 — integrated Procurement Intelligence acceptance

After #52, #50 and #51 have stable baselines, run one integrated evaluation:

`query -> ranked top-K -> selected procurement -> document package -> completeness -> frozen independent truth -> Tender Agent analysis/report -> comparator -> Product Owner verification`

This must attribute quality loss to the correct stage rather than letting downstream analysis tuning hide upstream search/source failures.

No real TKP is required for this phase.

## 9. Useful parallel work while real TKP is unavailable

### P1 — public-offer Supplier Engine dry runs

Exercise SE-001..004 on real GOODS procurements using only public offer evidence. This validates discovery, matching, evidence retention, enrichment and comparison-read-model behavior but is not real Supplier/TKP commercial acceptance.

### P1 — real-TKP readiness package

Prepare/validate the input template so the first genuine TKP can be registered immediately: supplier identity, position mapping, price/currency, VAT, MOQ, delivery, validity, source artifact and unresolved fields.

### P1 — controlled local-LLM multi-case reliability

Measure repeated local LLM completion using the DOCUMENT-QA truth set instead of weakening deterministic fallback/evidence rules.

### P2 — electrical/domain ontology

Improve aliases, model/article normalization, standards, characteristic names and truth packs because they can improve procurement relevance, technical extraction and supplier matching simultaneously.

### P2 — operator UX / explainability

Improve evidence-backed operator friction only: search score breakdown, why-result-matched, completeness reason, fact provenance, missing-data state and review/audit links.

### P2 — source expansion

223-FZ and private industrial procurement remain planned but should not dilute the current 44-FZ quality benchmark. Establish the 44-FZ baseline first, then add each source through a separate connector/acceptance contract.

### P2 — repository governance

`main` branch protection / required checks remain a separate engineering-hygiene item and are not the current product P0.

### P3 — historical P8.05 SOAP temporal health

Keep separate from the current public-read-only product path.

## 10. Governance debt

Historical PILOT-001 issue #23 remains formally open/stale while later development proceeded on the assumption that the pilot hardening gate had passed. Reconcile against final PO replay evidence, but do not restart product work solely because issue bookkeeping is stale.

## 11. Deferred / not authorized

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

## 12. Updated critical path

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
  ├──────────── while waiting ─────────────┐
  ↓                                       ↓
BENCHMARK-PIPELINE-001 (#52)          Supplier public-offer dry runs
  ↓
blind AI labeling + review states
  ↓
  ├───────────────────┐
  ↓                   ↓
DISCOVERY-QA-001   DOCUMENT-QA-001
search quality      document quality
  └─────────┬─────────┘
            ↓
INTEGRATED SEARCH -> DOCS -> ANALYSIS ACCEPTANCE
            ↓
PRODUCT OWNER FINAL BENCHMARK VERIFICATION
            ↓
when genuine TKP arrives
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

## 13. Immediate next step

Implement **BENCHMARK-PIPELINE-001 (#52)** before collecting 30–50 cases.

The first deliverable is the benchmark contract and blind-evaluation workflow, not a large corpus and not search tuning:

`schemas -> bundle boundaries -> blind evaluator input -> frozen label -> Tender Agent output ref -> comparator -> review state -> scorecard`

After this skeleton is tested on 1–3 calibration cases, scale collection automatically and start the DISCOVERY-QA / DOCUMENT-QA baselines.

## 14. Roadmap principle

While a downstream gate is blocked only by unavailable real-world input, move engineering effort to the highest-leverage upstream quality work that can be independently validated. Automate repetitive benchmark construction, keep evaluator/system independence, preserve source grounding, and retain explicit Product-Owner verification for the accepted benchmark release.