# SignalLock v0.10 — Fourth-order hardened checkpoint

## Promotion status

**V0–V6 + V7 qualification/execution/replay/evidence-boundary tooling: PASS after fourth-order hardening.**

**V7 multilingual model-quality qualification: NOT EXECUTED.** A genuine independently human-authored/reviewed Hindi/Telugu holdout and a fresh live provider-backed run are still mandatory.

## v0.10 controls now enforced

- Hindi/Telugu explicit negation is independently checked against action polarity, modality, and required/prohibited placement.
- Qualification receipts require provider-reported response ID and exact model identity.
- Provider configuration is verified against code-owned runtime configuration, not manifest-supplied configuration.
- Checkpoint format 4.0 binds every case to origin and execution run IDs.
- Successful case evidence retains exact provider structured output and SHA-256; replay reconstructs the candidate contract from it.
- Blind-review mapping format 3.0 binds opaque review IDs to authored task/content hashes.
- Strict V7 requires English authoritative sources and semantic source-family diversity.
- Author/reviewer identities are canonicalized against zero-width/format-character aliases.
- Public live sessions use short-lived server-side capabilities; the master token is not placed in the browser cookie.
- API version is derived from the canonical package version.
- Private V7 review/orchestration artifacts are ignored by source control under their actual generated filenames.

## Frozen runtime identity

- Release ID: `signallock-v0.10-fourth-order-hardened`
- Runtime-tree SHA-256: `2610370ce48baa404dc975e3e71a972d0546604a90bde0cabfff8f7de6ca659d`
- Trusted-manifest preflight runtime check: **PASS**.
- V7 execution readiness: **BLOCKED only on missing real provider credential + genuine human-reviewed sealed holdout**.
- V8 unlock with no V7 result: **LOCKED**, as required.

## Regression evidence

- Automated tests: **184/184 PASS**.
- Fourth-order hardening regressions: **14/14 PASS**.
- DEV benchmark: **108 cases**.
- Unsafe PASS: **0/76**.
- Unsafe BLOCK: **76/76**.
- Clean PASS: **32/32**.
- Clean BLOCK: **0/32**.
- Post-repair forensic audit: **PASS**.
- Second-order relational audit: **PASS**.
- Original fourth-order exploit retest F-1001–F-1010: **all blocked; 0 Critical/High unblocked**.

## Current gate

Do not promote to V8/submission until a genuine fresh V7 run has:

- a strict independently reviewed Hindi/Telugu holdout sealed to this exact v0.10 runtime/provider/model;
- 24/24 live cases;
- 0 checkpoint-recovered cases;
- 0 provider-error cases;
- unique exact-model provider receipts with retained replayable structured output for every successful case;
- all semantic V7 thresholds passing;
- fresh replay verification passing; and
- `scripts/check_v8_unlock.py` exiting 0.

Provider receipts and reviewer metadata remain audit/process evidence, not third-party cryptographic attestations.
