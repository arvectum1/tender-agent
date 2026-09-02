# PILOT-001-D08.1: Source-First GOODS Extraction

## Forensic Baseline

D08 audited five REPORT_READY cases: 23 material source facts were identified manually; zero entered structured extraction. Eight rich documents were available and zero were used by the GOODS source extractor. The old fallback generated generic templates, which D04 correctly rejected because they had no concrete evidence.

## Invariants

- Every text-bearing procurement document is eligible for conservative source-fact extraction regardless of filename or legacy `document.role`.
- Requirements are source-derived and carry document, file identity, locator, and exact excerpt at extraction time.
- Generic procurement checklists are not procurement facts. They may only appear as operator questions or missing-information prompts.
- `semantic_concrete_v2` remains the independent fail-closed evidence gate.

## Policies

- `source_first_all_text_v1`
- `content_aware_procurement_role_v1`
- `source_derived_goods_v1`

## Follow-up Gate

After merge, run controlled historical source-truth replay for cases 04, 05, 06, and 08. Case 03 is diagnostic only because rental scope semantics remain D07 work.
