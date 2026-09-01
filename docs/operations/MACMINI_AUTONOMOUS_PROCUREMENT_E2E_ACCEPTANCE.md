# Mac mini autonomous procurement E2E acceptance

Date: 2026-09-01
Status: PASS
Canonical merge PR: #21
Superseded draft PR: #20

## Runtime baseline

Pre-commit runtime HEAD:
`f6e9e23f1150972afaa87eeaed522069f49bf34b`

The successful runtime included uncommitted repository-owned corrections. The
source-controlled runtime acceptance commit places those corrections under source control:

`155f97e563206993f2a315b4e47c9d1391538781`

Canonical merge commit on `main`:

`b07d4eff59c5657dfd6f261437330bfb42b49828`

## Tests

Focused final regression suite:
`54 passed, 9 warnings`

Repository secret scan:
`clean`

CI run `#278` completed `SUCCESS` on the exact accepted source head before merge.

## Product transport

Classification:
`PRODUCT_TRANSPORT_PASS`

TLS:

- certificate verification: `CERT_REQUIRED`
- hostname verification: `true`
- minimum TLS: `TLS >= 1.2`
- source-controlled direct route: `true`
- TLS verification disabled: `false`

## Real E2E

Marker:
`MACMINI_AUTONOMOUS_PROCUREMENT_E2E_REPORT_READY`

Selected procurement:
`0373100107026000032`

Relevance:
threshold `20` passed

Run ID:
`toa-run-20260901074713-d6bae8`

Documents:
`5 files downloaded`

Analysis mode:
`llm_tender_operator_provider`

LLM invoked:
`true`

Fallback:
`false`

LLM evidence event:
`llm_analysis_completed`

HTML report SHA256:
`6ca3f39b51ee90adb0f5cce626dae504f7b08c87d6398a100bf1daff1a8ec9bf`

## Safety

- public discovery read-only
- no procurement submission
- no ETP login
- no captcha bypass
- no digital signature
- no supplier email/RFQ send
- no cloud LLM
- no TLS verification weakening
- no ARV-001 frozen evidence mutation

## Acceptance result

`PASS`

Target flow proven on the Mac mini:

public EIS search
-> deterministic selection
-> public document intake
-> completeness gate
-> local LLM analysis
-> HTML report
