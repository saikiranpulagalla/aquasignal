# SignalLock v0.11 — Branch Reconciliation / Provider-Retrieval Evidence Hardening Report

## Executive result

**Promote the combined tooling/runtime to v0.11. Do not claim V7 multilingual qualification.**

The v0.10 fourth-order branch and the provider-retrieval branch had diverged. v0.10 contained newer semantic/process protections but configured qualification calls as non-stored; the other branch could re-fetch stored provider responses but was based on an older runtime. Spending the human holdout on either branch would have left one known strength behind.

v0.11 starts from v0.10 and layers only the remote provider-evidence machinery onto it.

## Merge invariants preserved

The reconciliation explicitly preserves these v0.10 controls instead of replacing them:

- native Hindi/Telugu negation guard;
- strict provider-reported model identity;
- code-owned provider-config fingerprint;
- checkpoint format with origin/execution run identity;
- exact raw structured-output retention and candidate-contract reconstruction;
- blind-review task/content binding;
- source-family diversity and English source-language enforcement;
- Unicode-normalized role independence;
- hardened live-session capability cookies;
- canonical project/API versioning.

## New evidence boundary

Strict V7 now has two independent verification layers after execution.

### 1. Local deterministic replay

The saved raw provider structured output is hash-checked, reparsed through the frozen semantic guard/extraction path, and required to reconstruct the exact candidate contract consumed by the verifier. Metrics and the V7 gate are recomputed from case evidence.

### 2. Remote provider retrieval

For qualification only, OpenAI requests are stored. The verifier later retrieves each response and its input items from the provider and requires agreement on:

- response ID and exact provider-reported model;
- completed/stored state;
- case/run/holdout/runtime audit metadata;
- exact candidate-language user input;
- exact frozen extraction system prompt;
- exact structured output text/hash;
- reconstructed candidate contract/hash.

A locally fabricated response ID, locally changed output, changed stored input, changed prompt, changed metadata, or non-stored response fails closed.

## V8 promotion change

V8 no longer relies only on local result + replay receipts. It performs a fresh provider retrieval verification and cross-checks that result against the persisted provider-verification evidence before unlock.

## Adversarial regression coverage

The provider-retrieval suite specifically rejects:

1. fabricated/nonexistent response IDs;
2. wrong stored candidate input;
3. wrong stored system prompt;
4. modified remote output;
5. provider metadata mismatch;
6. non-stored responses;
7. ordinary extraction accidentally enabling storage; and
8. strict V7 accidentally disabling storage.

## Validation

- Full suite: **192/192 PASS**.
- DEV: **0/76 unsafe PASS; 76/76 unsafe BLOCK; 32/32 clean PASS**.
- Post-repair audit: **PASS**.
- Second-order relational audit: **PASS**.
- Fourth-order regressions: **14/14 PASS**.
- Provider-retrieval regressions: **8/8 PASS**.

## Remaining limitation

Retrievability is stronger evidence than a locally invented receipt, but it is not equivalent to a provider-signed attestation. Final claims must keep that distinction. Real human authoring/review and a real live run remain external prerequisites.
