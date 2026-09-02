# PILOT-001-D04.5

## Trigger

Fresh Mac mini GOODS run `0131200001026005651` exposed `D04.4_FALSE_CONCRETE_EVIDENCE_BINDING`.

## Root Cause

The previous matcher allowed weak lexical overlap and generic whole-document candidates to bind concrete ГОСТ/ТУ, safety, and delivery requirements. The generated excerpt was not revalidated against the claim.

## Policy

`semantic_concrete_v1` is applied before lexical scoring and after excerpt construction. Concrete standards, values, safety concepts, logistics concepts, and model-like identifiers must be supported by the candidate text itself. Unsupported rows become `INSUFFICIENT_EVIDENCE` and retain no concrete assertion fields.

The existing external binding marker `goods_claim_evidence_binding_v1` is unchanged. The additive `fallback_evidence_matching_policy` is exposed through `runtime_analysis`. The legacy `final_recommendation.trace` remains a string.

## Safety Boundary

This change only improves deterministic evidence provenance. It does not enable procurement submission, ETP mutation, supplier communication, EDS use, or any other external action.

## Verification

Focused coverage includes exact and mismatched standards, numeric context/value matching, safety, delivery, IP values, whole-document safety, excerpt validation, mixed rows, fail-closed output, and D04.2/D04.3 compatibility.
