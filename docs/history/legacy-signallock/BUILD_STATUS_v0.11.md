# SignalLock v0.11 — Fourth-Order + Provider-Retrieval Evidence Checkpoint

## Promotion status

**V0–V6 + V7 qualification/execution/offline-replay/provider-retrieval tooling: PASS.**

**V7 multilingual model-quality qualification: NOT EXECUTED.** A genuine independently human-authored/reviewed Hindi/Telugu holdout and a fresh live provider-backed run remain mandatory. **V8/submission remains locked.**

## Why v0.11 exists

Two strong branches had diverged after v0.9:

- v0.10 carried the newest fourth-order semantic/process hardening;
- the provider-retrieval branch carried a stronger evidence boundary that re-fetches stored OpenAI Responses instead of trusting only local receipts.

v0.11 reconciles them by starting from v0.10 and selectively adding provider retrieval. It does **not** replace v0.10 with the older branch.

## Preserved fourth-order controls

- Hindi/Telugu explicit-negation contradiction detection.
- Provider-reported model identity is mandatory for qualification evidence.
- Code-owned provider configuration binding.
- Checkpoint origin/execution run binding.
- Exact provider structured output retained and reparsed during offline replay.
- Blind-review mapping bound to authored task/content hashes.
- English authority-source requirement and semantic source-family diversity.
- Unicode format-character canonicalization for role identities.
- Server-side short-lived live-session capabilities; no master token in browser cookies.
- Canonical package/API version from `pyproject.toml`.

## Added provider-retrieval evidence controls

- Ordinary/demo OpenAI extraction remains `store=false`.
- Strict V7 qualification uses the code-owned `store=true` provider configuration.
- Every successful V7 request carries case/run/holdout/runtime audit metadata.
- Offline replay requires stored-response coverage and exact receipt metadata.
- Live provider verification re-fetches every response and its input items from OpenAI.
- Re-fetch validation binds response ID, model, status, storage state, audit metadata, user candidate text, frozen system prompt, raw structured output hash, and reconstructed candidate Safety Contract.
- V8 unlock requires a fresh provider re-fetch in addition to the persisted offline replay/provider-verification receipts.

## Regression evidence

- Automated tests: **192 / 192 PASS**.
- DEV benchmark: **108 cases**.
  - unsafe: **0 / 76 PASS; 76 / 76 BLOCK**.
  - clean: **32 / 32 PASS; 0 / 32 BLOCK**.
- Post-repair forensic audit: **PASS**.
- Second-order relational audit: **PASS**.
- Fourth-order hardening regressions: **14 / 14 PASS**.
- Provider-retrieval evidence regressions: **8 / 8 PASS**.
- Python compileall: **PASS**.

## Evidence boundary

Stored/retrievable provider responses materially strengthen auditability, but they are still not a provider-signed cryptographic attestation. Human reviewer IDs/timestamps also remain process evidence rather than cryptographic proof of identity.

## Current gate

Do not promote to V8/submission until a genuine fresh V7 run has all of the following:

1. a strict independently reviewed Hindi/Telugu holdout sealed to this exact runtime/provider/model;
2. 24/24 live cases;
3. zero checkpoint-recovered cases;
4. zero provider-error cases;
5. exact-model stored provider receipts for every successful case;
6. all semantic thresholds passing;
7. deterministic offline replay passing;
8. live provider retrieval verification passing; and
9. `scripts/check_v8_unlock.py` exiting 0.
