# SignalLock AI v0.6 — V7 Review-Integrity Hardening Report

## Executive verdict

**Implementation-side V7 review tooling is stronger and regression-clean, but V7 multilingual qualification is still intentionally NOT EXECUTED.**

The next legitimate gate requires real Hindi/Telugu candidate authoring, real independent reviewers, a sealed holdout, `OPENAI_API_KEY`, and a provider-backed run. No such evidence is fabricated in this checkpoint.

## Failure discovered in v0.5

The v0.5 workflow called its reviewer files “blinded,” but reviewers could infer hidden targets through three side channels:

1. `task_id` embedded labels such as `clean`, `modality`, `temporal`, etc.
2. `source_reference` distinguished official IMD clean seeds from post-freeze challenge seeds.
3. reviewer rows preserved the authoring packet order, which grouped clean and unsafe families predictably.

A fourth integrity problem was independent of label leakage: finalization trusted the task identifier but did not cryptographically bind a verdict to the exact source/candidate text shown to the reviewer. An edited review sheet could therefore produce a verdict over different content than the content later finalized.

## v0.6 repairs

- Reviewer-facing files now use unrelated opaque primary/secondary `review_id` values.
- Reviewer-facing files omit task IDs, source references, target decisions, expected decisions, fault classes, authoring instructions, candidate-author identity, and authority-review metadata.
- Primary and secondary review orders are independently shuffled and forced away from original authoring order.
- A **private** mapping file binds each opaque review ID to:
  - the hidden task ID;
  - SHA-256 of the exact reviewer-visible source/candidate content;
  - SHA-256 of the exact authored packet.
- Finalization rejects:
  - review rows with hidden fields reintroduced;
  - unexpected extra fields;
  - altered source/candidate text;
  - unknown/duplicate opaque IDs;
  - mapping files from another authored packet;
  - incomplete review coverage;
  - reviewer disagreement with the hidden target;
  - self-review under trivial case/whitespace identity aliases;
  - primary/secondary timestamps predating authority-contract review.
- Strict V7 quality validation also normalizes reviewer/author identities and requires timezone-aware `second_reviewed_at` for expected-BLOCK rows.

## Regression evidence

| Gate | v0.6 result |
|---|---:|
| Automated tests | **161/161 PASS** |
| DEV benchmark | **108/108** |
| Unsafe PASS | **0/76** |
| Unsafe BLOCK | **76/76** |
| Clean PASS | **32/32** |
| Post-repair forensic audit | **PASS** |
| Second-order relational audit | **PASS** |
| V7 review-integrity focused tests | **PASS** |
| End-to-end synthetic workflow dry run | **PASS** |

The synthetic workflow dry run exercised authoring-packet completion, opaque blinded review generation, private map generation, primary/secondary consensus finalization, strict V7 quality validation, and strict sealing. It is **workflow evidence only** and is not multilingual model-quality evidence.

## End-to-end dry-run evidence

The dry run produced 24 primary + 24 secondary reviewer rows. Reviewer-facing JSON contained no hidden field names (`task_id`, `fault_class`, `target_decision`, `source_reference`, `author_id`). Strict finalization reported:

- 24 rows
- 18 unique source texts
- 24 unique candidate texts
- all 7 required fault classes
- 3 reviewer identities
- 2 candidate authors
- 12 Hindi + 12 Telugu rows

The strict sealer completed when supplied the frozen external runtime trust anchor.

## Frozen runtime identity

- Release ID: `signallock-v0.6-v7-review-integrity-hardened`
- Runtime tree SHA-256: `8d8dea2f85866e061e4623ac46b1cf261243741aab1cdc8b188c46992957e12d`

The packaged-release path is considered trusted only when `SIGNALLOCK_TRUSTED_RUNTIME_SHA256` is supplied externally with that exact digest.

## Current preflight

With the correct external runtime digest, V7 preflight still exits non-zero as intended because:

- `OPENAI_API_KEY` is absent;
- the real human-reviewed Hindi/Telugu holdout is not sealed.

The preflight reports runtime code clean and all qualification tooling present.

## Required next sequence

1. Freeze this v0.6 package and model ID.
2. Configure `OPENAI_API_KEY`.
3. Fill source-contract drafts using the live provider.
4. Human-review each unique authority contract.
5. Have real human candidate authors produce Hindi/Telugu candidates.
6. Generate opaque blinded primary/secondary review sheets; **do not distribute the private mapping file**.
7. Collect independent human verdicts.
8. Finalize consensus; retire any disagreement rather than editing it into agreement.
9. Seal the final holdout against the external v0.6 runtime digest.
10. Run V7. Only that run may produce multilingual qualification metrics.

## Promotion decision

**Promote v0.6 as the qualification-tooling checkpoint. Do not promote to V8/submission yet.**
