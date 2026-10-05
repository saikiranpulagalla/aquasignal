# SignalLock v0.8 — V7 Replay-Evidence Hardening Report

## Executive result

v0.8 strengthens the last pre-live certification boundary. V7 previously persisted the final `PASS`/`REVIEW`/`BLOCK` decision and checkpoint metadata, but not the exact model-derived candidate Safety Contract that the verifier consumed. A saved decision therefore could not be independently replayed from the sealed holdout without calling the provider again.

v0.8 closes that gap. It **does not claim V7 multilingual qualification**; no human Hindi/Telugu holdout or live provider result has been fabricated.

## Failure found

A result could state a verifier decision without carrying enough evidence to independently reproduce that decision. This created four audit weaknesses:

1. the exact extracted candidate contract was absent;
2. aggregate metrics were trusted rather than independently recomputed from replayable case evidence;
3. checkpoint recovery count was an aggregate value rather than a per-case evidence property;
4. V8 had no independent fail-closed checker binding promotion to an unchanged, replay-verified V7 result.

## Repairs

- `V7CaseResult` now stores the exact candidate `SafetyContract` used by verification plus its canonical SHA-256.
- OpenAI extraction exposes an audit receipt containing response ID, response model, provider creation timestamp when available, usage metadata, and SHA-256 of the raw structured output text.
- Successful qualification cases require a non-empty provider response receipt.
- Checkpoint schema advanced from 2.0 to **3.0**.
- Every recovered case carries `recovered_from_checkpoint=true`; recovery metrics are recomputed from case evidence.
- `compute_v7_metrics()` is a single deterministic metric implementation shared by execution and replay.
- `verify_v7_evidence.py` validates sealed-case coverage, candidate-contract hashes, candidate provenance, source/candidate bindings, stored verifier outcomes, warnings/failures, aggregate metrics, and the final gate.
- `run_v7_multilingual.py` automatically performs offline replay verification immediately after writing its result and persists a result-hash-bound verification receipt.
- `check_v8_unlock.py` replays the evidence again and refuses promotion if the persisted receipt no longer hashes to the current result, the gate failed, a provider error occurred, or checkpoint recovery was used.
- Human holdouts, authored/reviewed sheets, private review mappings, and reviewed datasets are now explicitly ignored from source control by default.

## Verification

- Automated tests: **168/168 PASS**.
- New replay/tamper tests reject modified decisions, modified metrics, modified candidate contracts, and legacy evidence without provider-receipt coverage.
- DEV benchmark: **108 cases**.
- Unsafe: **0/76 PASS; 76/76 BLOCK**.
- Clean: **32/32 PASS**.
- Post-repair forensic audit: **PASS**.
- Second-order relational audit: **PASS**.
- Externally anchored release runtime resolves cleanly.
- V7 preflight exits non-zero only because the real API key and sealed human-reviewed holdout are absent.
- V8 unlock exits non-zero with no V7 result, as required.

## Evidence boundary

The provider receipt is useful audit metadata, **not cryptographic third-party proof** that OpenAI produced the recorded response. The replay verifier proves internal consistency of the saved provider-derived contract, verifier output, metrics and gate under the frozen runtime. Final claims must preserve this distinction.

## Promotion decision

**Promote qualification tooling to v0.8. Keep V7 model-quality qualification and V8/submission locked.**

The next legitimate promotion requires real human Hindi/Telugu authoring/review, strict sealing against this runtime, a fresh non-resumed provider-backed V7 run, zero provider errors, provider receipts on all successful cases, all V7 semantic thresholds passing, replay verification passing, and `check_v8_unlock.py` exiting 0.
