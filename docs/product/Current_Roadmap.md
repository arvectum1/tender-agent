# Tender Agent — Current Roadmap

Updated: 2026-09-05
Latest product-code baseline observed before roadmap documentation commits: `fa443a158ef1fa6e2f960ad5b2d59e3f9f99dba2`

## 1. Executive status

Tender Agent is past architecture recovery, Commercial MVP packaging, single-case proof-of-capability, and the main PILOT-001 analysis hardening cycle.

The repository now contains:

- the recovered canonical business registry `M-001..M-055`;
- Commercial MVP v1 and restricted-pilot packages;
- real Mac mini read-only procurement E2E;
- governed ARV-001 quality acceptance;
- PILOT-001 hardening through D04..D09.1;
- a new Supplier Engine branch with `SUPPLIER-ENGINE-001`, `002`, `002.1`, and `003` merged.

The product is still operator-assisted and restricted. No autonomous bid submission, EDS/signature, supplier email automation, or uncontrolled external execution is authorized.

## 2. Governance status: PILOT-001

PILOT-001 historical issue #23 remains technically OPEN and its body is stale: it still describes the earlier D04 closure gate.

However, later repository history shows the post-D04 hardening sequence completed through:

- D08.1 source-first GOODS extraction;
- D08.2 source-fact recall/retention;
- D07 evidence-based procurement scope semantics;
- D07.1 semantic scope preservation through serialization;
- D09 scope-consistent operator output;
- D09.1 scope-consistent RFQ draft.

PR #42 (`SUPPLIER-ENGINE-001`) explicitly records the working assumption that `PILOT-001 is already closed PASS on the current main baseline` and starts the agreed next Supplier Engine workstream.

Therefore the current state is:

- **product-development reality:** PILOT-001 has exited the critical path and Supplier Engine development has started;
- **issue bookkeeping:** issue #23 is still open/stale and should be reconciled/closed only against the final PO replay evidence.

This bookkeeping inconsistency is governance debt, not a functional blocker for current Supplier Engine work.

## 3. Canonical architecture coverage

Locked registry: `M-001..M-055`.

Repository governance records:

- canonical exact implementation: `M-001..M-048` and `M-051`;
- bounded internal metadata/control implementation: `M-049`, `M-050`;
- reconciled late slots, explicitly not full runtime modules:
  - `M-052` Notification Layer — `PLATFORM_ONLY`;
  - `M-053` Red Flag Registry — `GOVERNANCE_ONLY`;
  - `M-054` Master Dashboard — `PLATFORM_ONLY`;
  - `M-055` SaaS Productization Tracker — `GOVERNANCE_ONLY`.

The roadmap is therefore no longer about implementing the module registry from zero. The job is to operationalize the implemented modules into a repeatable real tender-business lifecycle.

## 4. First-wave lifecycle — actual maturity

### Block A — Platform skeleton

Status: **implemented and operationally exercised**.

Deal/status/document/audit foundations, controlled workflow/runtime contours, access boundary, external storage/readiness, operator workspace, evidence and report flows are present.

### Block B — Intake & analysis

Status: **most mature / deeply validated**.

Current real 44-FZ flow:

`public search → relevance selection → document intake → completeness → evidence-grounded analysis → human report`.

PILOT-001 materially hardened evidence binding, numeric units, source-fact recall, procurement scope semantics, downstream operator guidance, and RFQ semantics.

Remaining source robustness debt:

- D05 incomplete document sets — safe fail-closed behavior is correct; root cause remains worth investigating later;
- D06 EIS `unsupported_layout` — unresolved single source-layout case.

### Block C — Supplier Engine

Status: **ACTIVE CURRENT WORKSTREAM**.

Canonical supplier modules already exist, and Commercial MVP has manual supplier/TKP flows. The new Supplier Engine workstream is turning that into stronger automated discovery/matching while preserving manual external actions.

Merged increments:

#### SUPPLIER-ENGINE-001 — position-level supplier offer matching

- unified procurement-position / supplier-offer contract;
- per-offer source attribution;
- deterministic identity matching by article/model/brand/manufacturer/title;
- VAT/MOQ/lead-time normalization without invented defaults;
- conflicting explicit article numbers rejected;
- ranked matches without autonomous commercial winner selection.

#### SUPPLIER-ENGINE-002 — public offer discovery adapter

- position-aware public web search queries;
- public search result → `SupplierOfferCandidate` conversion;
- source-evidenced price/VAT/MOQ/delivery extraction;
- marketplace filtering and supplier-domain deduplication;
- direct handoff into the SE-001 ranking core;
- provider failures propagated without fabricated offers.

#### SUPPLIER-ENGINE-002.1 — RU/EN identifier evidence normalization

- Cyrillic/Latin transliteration support for article/model identifiers;
- prevents false misses such as `КМИ-22510` vs `KMI-22510`;
- empty search-result titles no longer receive fabricated procurement-position fallback text.

#### SUPPLIER-ENGINE-003 — product-page enrichment

- bounded fetch of public supplier product pages;
- reject private/local/unsafe targets and unsafe redirects;
- extract source-backed price, VAT, MOQ, delivery, availability and identifiers;
- preserve per-field evidence/source URL;
- keep missing terms unknown rather than invent defaults.

Still intentionally closed:

- supplier email/outbound automation;
- autonomous RFQ send;
- autonomous ordering or purchase;
- unattended supplier negotiation.

### Block D — Finance / risk / approval

Status: **implemented in bounded operator form; awaiting stronger real-cycle integration with the new Supplier Engine**.

Commercial workspace already supports:

- manual TKP registration;
- quote comparison;
- deterministic cost model;
- cash-gap estimate;
- financing strategy;
- finance memo;
- contract risk;
- CEO approval package;
- bid-readiness status.

The next strategic integration is to feed SE-001..003 supplier offers and manual TKPs into one comparison/economics decision contour.

### Block E — Bid / submission / outcome

Status: **canonical/recovery coverage exists; external execution remains restricted**.

The commercial workspace already creates bid document collection, bid package skeleton and completeness/readiness state. Final submission remains manual; no ETP mutation, EDS/signature, or autonomous submission is open.

## 5. Product maturity timeline

### Completed phases

- architecture recovery and registry reconciliation;
- Launch/controlled internal usage packages;
- Commercial MVP v1;
- controlled commercial pilot package;
- design-partner pilot package;
- restricted paid pilot operations setup (PP0);
- real partner folder runner (PP1);
- Tender Operator RFQ-first refinement (PP1R);
- ARV-001 quality freeze;
- real Mac mini read-only E2E;
- PILOT-001 hardening D04..D09.1.

### Current phase

**Supplier Engine operationalization.**

SE-001..003 are merged. The system can now match procurement positions to supplier offers, discover public offers, normalize identifiers, and enrich from product pages under bounded safety rules.

### Next product phase

**Unify Supplier Engine outputs with TKP / quote comparison / economics / risk / owner decision.**

Target cycle:

`procurement position → public offers + manual TKP → normalized offer set → comparison → economics → contract risk → GO/NO-GO → audit trail`.

### Following phase

Controlled bid package lifecycle:

`required docs → collected docs → completeness → package → ready_for_human_submission → manual submission → receipt → outcome`.

This is the path to proving the full first-wave business lifecycle without prematurely opening unsafe autonomy.

## 6. Recommended next Supplier Engine increment

No canonical `SUPPLIER-ENGINE-004` task is currently recorded in the repository.

Recommended next increment:

**comparison-ready offer set / M-021 handoff**

Scope:

1. merge enriched public offers and manual TKP offers into one normalized per-position offer set;
2. preserve `source_type`, source URL/artifact ref, evidence for every commercial field;
3. keep price/VAT/MOQ/lead time/availability unknown when not evidenced;
4. separate eligibility/match quality from commercial ranking;
5. feed only eligible candidates into existing quote comparison/economics;
6. produce explicit unresolved-data flags instead of choosing a fake winner;
7. remain read-only and never contact suppliers automatically.

After that, run a real operator-controlled supplier/economics cycle on several GOODS procurements.

## 7. Parallel workstreams

### P0 — Supplier Engine integration

SE-001..003 are merged. Next: comparison-ready offer set + M-021/TKP/economics handoff + real-cycle validation.

### P1 — PILOT-001 governance reconciliation

Resolve the mismatch between stale/open issue #23 and the later repository assertion that PILOT-001 is PASS. Do not redo product work unless the final replay evidence actually shows a blocker.

### P1 — Controlled LLM multi-case reliability

Single-case local LLM E2E passed, but historical multi-case evidence was fallback-heavy. Validate repeatability separately without weakening deterministic evidence grounding.

### P1 — Commercial/legal pilot readiness

Keep local data handling, restricted pilot terms, feedback capture, human review and manual external actions mandatory before broader customer circulation.

### P2 — D05 document completeness

Classify upstream EIS incompleteness vs intake coverage gap; preserve fail-closed behavior.

### P2 — D06 source-layout robustness

Reproduce/classify `unsupported_layout` before changing parsers.

### P2 — Source expansion

Keep the accepted 44-FZ contour stable and add other procurement sources as separate connectors/contracts. 223-FZ and private industrial sources should not silently change the accepted 44-FZ path.

### P2 — Domain ontology / electrical vertical

Improve exact characteristics, standards, normalization, aliases and truth packs to strengthen supplier matching and technical analysis.

### P2 — Operator UX / observability

Prioritize evidence-driven improvements only: run queue, supplier candidate review, failure reasons, report/review state, audit links, workload visibility.

### P2 — Repository governance

`main` branch protection / required checks remain unenforced at repository level. Fix when admin/tooling constraints allow.

### P2 — Arvectum OS integration

Continue as a consumer/orchestrator of Tender Agent contracts, but do not make OS integration a prerequisite for Tender Agent business-cycle validation.

### P3 — historical P8.05 SOAP temporal health

Issue #1 remains separate maintenance/governance debt and must not be treated as a blocker for the current public-read-only product contour.

## 8. Deferred / not authorized

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

## 9. Critical path

```text
ARV-001 quality freeze ✅
  ↓
Mac mini real E2E ✅
  ↓
PILOT-001 D04..D09.1 hardening ✅
  ↓
Supplier Engine 001 matching ✅
  ↓
Supplier Engine 002 public discovery ✅
  ↓
Supplier Engine 002.1 identifier normalization ✅
  ↓
Supplier Engine 003 product-page enrichment ✅
  ↓
COMPARISON-READY OFFER SET + M-021/TKP HANDOFF ← CURRENT NEXT
  ↓
REAL SUPPLIER + TKP + ECONOMICS + RISK + GO/NO-GO CYCLE
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

## 10. Roadmap principle

The repository already has broad canonical module coverage. Roadmap priority is now determined by **business-cycle evidence and integration quality**, not by the number of module files or endpoints implemented.

The strategic job is to make the existing modules work together on real procurements: source-bound analysis → supplier offers → TKP/economics → risk → owner decision → bid package → manual submission/outcome, while retaining explicit human control boundaries.
