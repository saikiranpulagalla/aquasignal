# SignalLock v0.9 — V7 evidence-boundary checkpoint

## Promotion status

**V0–V6 + V7 qualification/execution/replay/evidence-boundary tooling: PASS.**

**V7 multilingual model-quality qualification: NOT EXECUTED.** A genuine independently human-authored/reviewed Hindi/Telugu holdout and fresh live provider-backed run are still mandatory.

## New evidence-boundary controls

- Production V7 replay requires a manifest created by the strict V7 sealer; a generic manifest cannot certify V7.
- Replay recomputes the strict holdout quality block directly from the exact sealed rows and rejects any manifest quality mismatch.
- Replay re-verifies the manifest's code/runtime identity and provider/model/config/prompt/schema fingerprint against the frozen runtime.
- Result-level provider/model fields must agree with the execution binding.
- Every successful provider receipt must report the exact frozen model.
- Provider response IDs must be unique across successful V7 cases; receipt reuse is fail-closed.
- Provider structured-output SHA-256 fields are format-validated before the receipt is accepted as audit evidence.
- V8 unlock additionally binds the persisted replay receipt to the exact manifest file hash, run ID, provider, model, gate, immutable runtime identity, and runtime-tree hash.
- Coordinated edits to manifest quality + result metrics + the persisted verification receipt no longer bypass fresh replay because quality and runtime bindings are independently recomputed.

## Regression evidence

- Automated tests: **170/170 PASS**
- DEV benchmark: **108 cases**
- Unsafe PASS: **0/76**
- Unsafe BLOCK: **76/76**
- Clean PASS: **32/32**
- Post-repair forensic audit: **PASS**
- Second-order relational audit: **PASS**
- New manifest/provider-receipt adversarial tests: **PASS**

## Evidence limitation

Provider response receipts remain audit metadata rather than cryptographic attestations signed by the external provider. Human reviewer identity/timestamp fields are also process evidence rather than cryptographic identity proof. Do not overstate either property.

## Current gate

Do not promote to V8/submission until a genuine fresh V7 run has:

- strict independently reviewed Hindi/Telugu holdout sealed to this exact runtime/provider/model;
- 24/24 live cases;
- 0 checkpoint-recovered cases;
- 0 provider-error cases;
- unique exact-model provider receipts for every successful case;
- all semantic V7 thresholds passing;
- fresh replay verification passing; and
- `scripts/check_v8_unlock.py` exiting 0.
