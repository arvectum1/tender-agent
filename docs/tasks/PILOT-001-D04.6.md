# PILOT-001-D04.6

## Scope

D04.6 strengthens GOODS fallback evidence binding after the final fresh
multi-case validation reproduced a P0 false concrete binding for registry
`0329100004326000031`. The claim `Накопитель внутренних данных 8 ТБ` was bound
to an excerpt containing `4 ТБ` and `3 ТБ`.

## Root Cause

The prior numeric matcher treated units as optional. A material numeric claim
could therefore degrade to a bare-number anchor, while whole-document scoring
and separately recomputed excerpts could select unrelated evidence.

## Policy

The binding policy remains `goods_claim_evidence_binding_v1`. The semantic
matching policy is bumped to `semantic_concrete_v2` because numeric evidence
semantics are materially stricter.

Invariant:

> A material numeric assertion carrying an explicit unit may bind only to
> evidence containing the compatible value/unit pair in supporting local
> context; otherwise it fails closed.

## Behavior

- Storage units `КБ`, `МБ`, `ГБ`, `ТБ` and `KB`, `MB`, `GB`, `TB` are normalized by unit family; `KiB`, `MiB`, `GiB`, and `TiB` remain distinct families.
- Units are never converted automatically, so `8 ТБ` does not equal `8192 ГБ` or `8 TiB`.
- An unknown attached unit cannot degrade to a bare number.
- Numeric matching requires exact value/unit and local claim context.
- The excerpt selected during semantic validation is the excerpt persisted in `trace.evidence_map`.
- Existing standards, safety, delivery, IP, and day-based numeric checks remain fail-closed.

## Regression Coverage

`tests/test_pilot_001_d04_6_unit_qualified_numeric_binding.py` covers exact
storage values, Cyrillic/Latin normalization, wrong capacities/units,
unrelated values and objects, unknown units, whole-document excerpts, day
compatibility, and mixed bound/insufficient rows.

The historical Case 08 shape is represented by the `8 ТБ` claim against
`4 ТБ`, `3 ТБ`, and unrelated `8 шт.`; expected output is
`INSUFFICIENT_EVIDENCE` with no evidence IDs.
