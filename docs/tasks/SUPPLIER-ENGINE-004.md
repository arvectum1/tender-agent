# SUPPLIER-ENGINE-004 — Comparison-ready offer set + M-021/TKP handoff

## Goal
Unify Supplier Engine public-offer outputs and manual quotation/TKP inputs into one comparison-ready per-position offer set without inventing commercial facts or promoting public-web ranking into a formal supplier selection.

## Baseline
Canonical repository: `arvectum1/tender-agent`

Branch: `work/supplier-engine-004-comparison-ready-offer-set`

Parent main observed when task was opened: `36a6f6348fba953b56feb7634a12388fad7d45d2`.

Relevant existing contracts:
- `src/modules/quote_comparison/position_matching.py` — procurement-position / supplier-offer normalization and ranking;
- `src/modules/supplier_search/position_offer_discovery.py` — public-web discovery to `SupplierOfferCandidate`;
- `src/modules/supplier_search/product_page_enrichment.py` — source-backed enrichment;
- `src/modules/quote_repository/**` — formal quotation/TKP records;
- `src/modules/quote_comparison/**` — M-021 formal quote comparison and recommendation.

## Product boundary
Public discovery/matching is evidence gathering, not commercial supplier selection.

These concepts must remain distinct:
1. public offer candidate;
2. eligible/ranked offer;
3. matching `best_offer_id`;
4. formal quotation/TKP;
5. M-021 quote-comparison recommendation;
6. downstream selected supplier.

A public candidate MUST NOT become a formal quotation, recommendation, or selected supplier without the required evidence and explicit contract bridge.

## Required implementation

### 1. Comparison-ready offer model
Introduce a bounded per-position normalized offer-set contract that can represent both:
- enriched public-web offers;
- formal/manual commercial quotations.

Every offer must preserve at minimum:
- stable offer/source identity;
- position identity;
- supplier identity/label when evidenced;
- `source_type`;
- source URL or artifact reference as applicable;
- item identity fields;
- price;
- currency;
- VAT mode/rate;
- MOQ;
- delivery time;
- availability when available;
- match/eligibility state;
- explicit unresolved-data flags;
- field/source provenance sufficient to distinguish observed, normalized and unknown values.

Do not invent defaults for missing commercial terms.

### 2. Public-offer adapter
Adapt `SupplierOfferCandidate` / product-page enrichment output into the comparison-ready contract.

Rules:
- only evidence-backed values are populated;
- missing values stay unknown;
- matching eligibility and match score are retained;
- `best_offer_id` remains a matching hint only;
- public offers are never marked as formal quotation/TKP merely because they have a price.

### 3. Manual quotation/TKP adapter
Adapt existing formal `QuoteRecord` / quote-set data into the same comparison-ready contract without breaking existing quote repository semantics.

Rules:
- preserve quote/supplier/artifact references;
- preserve quote status;
- preserve formal quoted amount/currency;
- retain provenance to the quotation record/artifact;
- do not backfill commercial fields that the existing quote contract does not evidence.

### 4. Unified per-position offer set
Provide a deterministic service that combines eligible public offers and relevant formal quotation/TKP offers for the same procurement position.

The service must:
- return stable deterministic ordering;
- preserve source type and provenance;
- deduplicate only when identity/provenance make equivalence safe;
- expose unresolved-data flags;
- separate `match/eligibility` from `commercial comparison/recommendation`;
- never fabricate a winner.

### 5. M-021 handoff
Add a bounded handoff from the unified offer set toward existing M-021/quote-comparison flow.

Required semantics:
- M-021 formal recommendation continues to require formal quotation-backed records under the existing verification/quote contracts;
- public-web offers may be surfaced as comparison context/candidates, but must not silently become `recommended_supplier_id`;
- if formal quotations are absent, output must explicitly state that formal M-021 recommendation is unavailable/not_ready rather than choose a public-web candidate;
- if formal quotations exist, preserve existing quote-comparison behavior and recommendation semantics.

Do not redesign M-021 scoring in this task.

### 6. API / operator surface
Expose the unified offer set through the narrowest existing service/router surface that fits the repository architecture.

The human-facing response must make source class and readiness explicit, so an operator can distinguish:
- public candidate;
- formal quotation;
- eligible/matched;
- comparison-ready;
- formal recommendation available/unavailable.

No supplier messaging, RFQ sending, ordering, ETP mutation, EDS, or autonomous external action.

## Acceptance criteria
1. Public and manual quotation offers can coexist in one per-position normalized offer set.
2. Source provenance survives normalization for every commercial field that is populated.
3. Unknown price/VAT/MOQ/delivery/availability stays unknown and produces explicit unresolved flags.
4. Public candidate ranking never creates a formal quotation, `recommended_supplier_id`, or downstream selected supplier.
5. Formal quotation-backed M-021 recommendation still works when valid quote + verification inputs exist.
6. No-formal-quote case returns an explicit not-ready/no-formal-recommendation state rather than a fake winner.
7. Existing Supplier Engine 001–003 behavior remains backwards-compatible unless a narrowly justified interface extension is required.
8. Existing quote repository / M-021 tests remain green.
9. New focused tests cover public-only, quote-only, mixed, missing-commercial-data, identity-conflict/deduplication, and deterministic ordering cases.
10. Full relevant regression suite passes with clean tracked tree.

## Non-goals
- no autonomous supplier selection;
- no supplier email/RFQ send;
- no negotiation;
- no purchase/order execution;
- no M-021 scoring redesign;
- no broad database redesign unless strictly necessary;
- no SaaS/multi-tenant work;
- no changes to PILOT-001 acceptance semantics.

## Definition of Done
- implementation and focused regression tests complete;
- relevant existing suites green;
- no public-web candidate promoted into formal selection without quotation-backed evidence;
- no invented commercial facts;
- branch is ready for PR to `main` with concise migration/compatibility notes if schema changes were required.
