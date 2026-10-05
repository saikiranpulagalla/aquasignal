# SignalLock v0.10 — Next Actions

1. Freeze this exact v0.10 package and externally record both the runtime-tree SHA-256 and package SHA-256.
2. Set `SIGNALLOCK_TRUSTED_RUNTIME_SHA256` to the published v0.10 runtime digest.
3. Freeze the exact intended `OPENAI_MODEL` and configure a real `OPENAI_API_KEY` only on the controlled qualification machine.
4. Generate/use the fixed V7 qualification packet; complete genuine human authority review and independent Hindi/Telugu candidate authoring.
5. Generate independently shuffled blinded primary/secondary review sheets. Keep `data/multilingual/v7_blind_review_map.json` private.
6. Collect genuine independent reviews; retire/replace disagreements rather than editing them into consensus.
7. Finalize and strictly seal `data/multilingual/v7_reviewed.jsonl` under this exact v0.10 runtime/provider/model.
8. Remove/archive any prior V7 checkpoint, result, and replay-receipt outputs so the qualification starts fresh.
9. Run `python scripts/run_v7_preflight.py`; require exit 0.
10. Run `python scripts/run_v7_multilingual.py` without `--resume`; require 24 live cases, zero provider errors, zero recovered cases, exact-model unique provider receipts, and passing semantic metrics.
11. Require the automatic replay-verification receipt to pass; optionally rerun `python scripts/verify_v7_evidence.py` independently.
12. Run `python scripts/check_v8_unlock.py`; require exit 0 before any V8/submission claim is frozen.
13. Externally archive the sealed holdout hash, strict manifest-file hash, result hash, replay receipt, runtime digest, and package digest with the final evidence.

Never present a resumed run, provider-error run, generic/non-strict manifest, model-mismatched/reused provider receipt, synthetic review workflow, edited evidence bundle, or a v0.9 result as v0.10 qualification evidence.
