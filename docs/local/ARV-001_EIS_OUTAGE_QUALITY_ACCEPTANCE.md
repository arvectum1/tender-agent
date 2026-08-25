# ARV-001 — governed quality acceptance under external EIS outage

This path exists only for the case where the frozen ARV-001 corpus has already
been independently reproduced from real EIS data, but current temporal EIS
health is externally blocked. It **does not** make P8.05 pass and it does not
replace the separate EIS health blocker.

Tracked external blocker: `#1`.
Design / implementation issue: `#2`.

## Invariants

- P8.05 remains strict and unchanged.
- Frozen baseline provenance must validate exactly.
- Exact corpus and provider-policy SHA-256 values must match the baseline.
- The repository must be clean and at the exact authorized HEAD.
- A human product owner must explicitly authorize one quality-only run.
- The acknowledgement is valid for at most 24 hours and is bound to one HEAD,
  baseline, corpus and policy.
- The acknowledgement is atomically consumed before the provider-capable child
  process starts. A consumed acknowledgement cannot be reused.
- No EIS request is made by this runner.
- No procurement submission, email, digital signature, or other external action
  is authorized.
- The acceptance output must retain
  `temporal_source_health=blocked_external_dependency` and
  `p805_status=BLOCKED_EXTERNAL_SOURCE`.
- OpenCode, Codex, ChatGPT, automation, or another agent must not invent the
  product-owner acknowledgement.

## Product-owner acknowledgement

Create the acknowledgement outside the repository. Replace the placeholders
only after the implementation is merged and the exact acceptance HEAD is known.
The descriptor SHA is the canonical compact JSON SHA-256 produced by the
repository helper, not a raw-file-byte hash.

```json
{
  "schema_version": "arv001-external-source-outage-ack-v1",
  "task_id": "ARV-001",
  "decision": "AUTHORIZE_QUALITY_ACCEPTANCE_ONLY",
  "acknowledgement_id": "<unique-id>",
  "acknowledged_by": "<human-product-owner-subject>",
  "actor_type": "human_product_owner",
  "acknowledged_at": "<ISO-8601 timestamp with timezone>",
  "approval_statement": "I authorize one ARV-001 quality-only acceptance run against the frozen real-EIS baseline while temporal EIS source health remains externally blocked.",
  "expected_head": "<exact-40-char-git-sha>",
  "baseline_id": "arv001-v2-6557c0fa0dcc",
  "baseline_descriptor_sha256": "<canonical-baseline-descriptor-sha256>",
  "corpus_sha256": "6557c0fa0dcc85bbab1a1e72a556505734c65eea6a29e649082eafbe80dc1d0a",
  "policy_sha256": "2fcb1db44eee3df5762410f892ad1f806221e811e356df4863108a3213db41d0",
  "external_blocker_code": "EIS_REPEATED_CODE_0_PROCESSING_ERROR",
  "temporal_source_health": "blocked_external_dependency",
  "generation_run_limit": 1,
  "external_actions_authorized": false
}
```

## Runner

Use a new isolated detached worktree at the exact authorized HEAD and new
private roots outside the repository:

```bash
python -m scripts.arv001.run_outage_quality_acceptance \
  --baseline-candidate-root <frozen-candidate-root> \
  --baseline-intake-root <frozen-intake-root> \
  --database-path <new-or-approved-local-sqlite> \
  --initialize-database \
  --data-dir <new-data-dir> \
  --approved-policy quality_gates/arv001/provider_policy.json \
  --acceptance-output-root <new-acceptance-output-root> \
  --binding-root <new-binding-root> \
  --product-owner-ack <ack-json-outside-repository> \
  --expected-head <exact-authorized-head>
```

Do not add `--initialize-database` when using an already-migrated isolated test
database.

## Success boundary

Success is distinct from a P8.05 pass:

- status: `QUALITY_ACCEPTANCE_COMPLETE_UNDER_EXTERNAL_SOURCE_BLOCKER`
- marker: `ARV-001_QUALITY_ONLY_UNDER_EXTERNAL_SOURCE_BLOCKER_COMPLETE`
- `p805_status=BLOCKED_EXTERNAL_SOURCE`
- `temporal_source_health=blocked_external_dependency`
- `quality_evidence_class=real_frozen_reproduced_eis`
- exactly one controlled invocation
- immutable artifact hashes present
- zero production DB, historical ARV-003, Git, and external-action mutations

After success, continue with the normal ARV-001 boundary: two genuine
independent human reviews, adjudication only if needed, deterministic quality
evaluation, and freeze only on `PASS + freeze_allowed=true`. Final freeze
evidence must preserve the external-source-health disclosure.
