# SignalLock v0.8 — V7 replay-evidence checkpoint

## Promotion status

**V0–V6 + V7 qualification/execution/evidence tooling: PASS.**

**V7 multilingual model-quality qualification: NOT EXECUTED.** It still requires a real independently human-authored/reviewed Hindi/Telugu holdout, an externally trusted frozen runtime digest, and a live provider-backed run.

## New replay-evidence controls

- Every successful V7 case stores the exact post-provider candidate `SafetyContract` used by the verifier.
- The stored candidate contract is SHA-256 bound inside the case evidence/checkpoint.
- Successful OpenAI calls retain an audit receipt: response ID, response model, provider timestamp when available, usage metadata, and SHA-256 of the raw structured output text.
- Qualification requires a provider receipt for every successful live case; older decision-only evidence cannot pass the v0.8 gate.
- Checkpoint format is now **3.0** and includes replayable case evidence.
- Every recovered case is explicitly marked `recovered_from_checkpoint`; aggregate recovery counts are recomputed from case evidence rather than trusted from a saved metric.
- `verify_v7_evidence.py` replays each stored candidate contract against its sealed source contract, validates provenance, recomputes the verifier result, recomputes aggregate metrics, and recomputes the V7 gate.
- Decision, contract, metric, gate, case-coverage, manifest, runtime, and result-hash tampering are fail-closed.
- `run_v7_multilingual.py` automatically writes a replay-verification receipt after every completed run.
- `check_v8_unlock.py` refuses V8 unless the persisted verification receipt still hashes to the unchanged V7 result and the replayed V7 gate passes with zero provider errors and zero checkpoint recovery.


## Regression evidence

- Automated tests: **168/168 PASS**
- DEV benchmark: **108 cases**
- Unsafe PASS: **0/76**
- Unsafe BLOCK: **76/76**
- Clean PASS: **32/32**
- Post-repair forensic audit: **PASS**
- Second-order relational audit: **PASS**
- Replay/tamper integrity tests: **PASS**

## Evidence limitation

The provider response receipt is an audit trail, **not a cryptographic attestation signed by OpenAI**. It materially improves traceability but must not be described as third-party cryptographic proof of provider execution.

## Current gate

Do not promote to V8/submission until a genuine fresh V7 run has:

- a strict human-reviewed Hindi/Telugu holdout sealed to this exact runtime;
- 24/24 live cases;
- 0 recovered checkpoint cases;
- 0 provider-error cases;
- provider receipts for every successful case;
- all semantic V7 thresholds passing;
- replay verification passing; and
- `scripts/check_v8_unlock.py` exiting 0.
