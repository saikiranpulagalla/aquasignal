# SignalLock v0.9 — Next Actions

1. Freeze this exact v0.9 package and externally record both its runtime-tree SHA-256 and package SHA-256.
2. Set `SIGNALLOCK_TRUSTED_RUNTIME_SHA256` to the published v0.9 runtime digest.
3. Freeze `OPENAI_MODEL` to the intended model and configure a real `OPENAI_API_KEY`.
4. Complete genuine human authority review and Hindi/Telugu candidate authoring from the fixed qualification packet.
5. Generate independently shuffled blinded primary/secondary review sheets; never expose the private mapping to reviewers.
6. Collect genuine independent reviews; retire/replace disagreements rather than editing them into consensus.
7. Finalize and strictly seal `v7_reviewed.jsonl` with `scripts/seal_v7_holdout.py` under this exact v0.9 runtime/model.
8. Archive/remove prior V7 checkpoint, result, and replay-receipt outputs.
9. Run `python scripts/run_v7_preflight.py`; require exit 0.
10. Run `python scripts/run_v7_multilingual.py` without `--resume`; require 24 live cases, zero provider errors, zero recovery, exact-model unique provider receipts, and passing semantic metrics.
11. Independently rerun `python scripts/verify_v7_evidence.py` if a second replay receipt is desired.
12. Run `python scripts/check_v8_unlock.py`; require exit 0 before any submission claim/polish is frozen.
13. Externally archive the sealed holdout hash, manifest-file hash, result hash, replay receipt, runtime digest, and package digest with the final submission evidence.

Never present a resumed run, provider-error run, generic/non-strict manifest, model-mismatched/reused provider receipt, synthetic review workflow, or locally edited evidence bundle as V7 qualification evidence.
