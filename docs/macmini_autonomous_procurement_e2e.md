# Mac mini autonomous procurement E2E

## Purpose

This development track proves one continuous local workflow:

`public procurement discovery -> deterministic relevance selection -> public documentation intake -> completeness gate -> local analysis -> HTML report`.

ARV-001 is now `CLOSED / FROZEN` on canonical `main`. The accepted ARV-001 human-facing baseline remains immutable; this E2E workflow reuses Product code but is a separate development track and must not rewrite the historical accepted source/evidence baseline or governance record.

## One-command runner

With the Tender Agent backend already running on the Mac mini:

```bash
python3 scripts/run_macmini_autonomous_procurement.py \
  --query "электротехническое оборудование" \
  --law 44fz \
  --min-relevance 20
```

Default backend: `http://127.0.0.1:8000`.

A successful run prints the marker:

`MACMINI_AUTONOMOUS_PROCUREMENT_E2E_REPORT_READY`

and saves a copy of the generated HTML under:

`company_agent_runs/macmini_autonomous_e2e/`.

A source/docs/runtime problem prints:

`MACMINI_AUTONOMOUS_PROCUREMENT_E2E_BLOCKED`

with a machine-readable code and details. No fake procurement or fake report is substituted.

## Flow

1. Public EIS search is called in read-only mode.
2. Existing deterministic supplier-profile relevance scores are used.
3. The highest-scoring card above the configured threshold is selected automatically.
4. The existing search-result handoff creates a procurement run.
5. Existing public-document/getDocs intake attempts to obtain the document set.
6. The existing completeness gate decides whether analysis is allowed.
7. If documents are ready, the existing analysis endpoint runs.
8. The existing report renderer produces HTML; the orchestrator saves a local copy.
9. Run events are inspected so the result says whether the LLM completed or the deterministic fallback was used.

The first increment supports the existing public 44-FZ search path only. 223-FZ should be added as a separate audited source path rather than silently treated as identical.

## Where the LLM is used

The backend currently requests controlled LLM analysis after deterministic document extraction has prepared source text. The controlled Tender Operator workflow uses the LLM for semantic/drafting tasks:

- requirements extraction/normalization;
- supplier questions;
- RFQ draft;
- contract-risk memo;
- optional quote normalization when quote inputs exist;
- optional preliminary bid-decision rationale when quote inputs exist.

Every section is schema-validated and remains human-reviewable. The LLM is not authorized to submit an application, send supplier email, sign, log into an ETP, or make a legally final decision.

On the Mac mini the intended default is the existing local OpenAI-compatible llama.cpp endpoint configured in `.env.macmini.example`, for example `http://host.docker.internal:8088/v1`. A cloud model is not required for this E2E proof.

## Where the LLM is NOT used

These stages remain deterministic/non-LLM:

- EIS/public HTTP discovery;
- procurement-card parsing;
- download and archive handling;
- XML metadata and purchase-object parsing;
- DOCX/XLSX/text extraction;
- relevance scoring and candidate ordering;
- document-set completeness;
- source/evidence identities and integrity checks;
- deterministic quote-table parsing when supported;
- arithmetic/economics calculations;
- safety/governance checks;
- HTML rendering and presentation compression.

If the local LLM is unavailable, the current backend records `stub_analysis_fallback` and uses the document-dependent deterministic fallback. The E2E summary makes that explicit; it never reports an LLM run that did not occur.

## Safety boundary

This runner performs no procurement-platform mutation. It does not:

- submit applications;
- send email/RFQ;
- use an ETP login;
- bypass captcha;
- use a digital signature;
- synthesize missing source documents;
- mutate ARV-001 accepted evidence or governance.

## Current proof boundary

The first run is a proof of the autonomous **read-only intelligence loop**, not autonomous tender participation. If EIS blocks public HTML or a complete document set cannot be obtained automatically, the correct outcome is `BLOCKED` with the source/document reason. That failure is useful evidence for the next connector/runtime increment.
