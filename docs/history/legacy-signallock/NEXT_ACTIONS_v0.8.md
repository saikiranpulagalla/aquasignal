# SignalLock v0.8 — Next Actions

1. Freeze this v0.8 package and externally record its runtime-tree SHA-256 and package SHA-256.
2. Set `SIGNALLOCK_TRUSTED_RUNTIME_SHA256` to the exact recorded runtime-tree digest.
3. Set the frozen `OPENAI_MODEL` and a real `OPENAI_API_KEY`.
4. Complete genuine human authority review and Hindi/Telugu candidate authoring from the fixed qualification packet.
5. Generate the blinded primary/secondary sheets and keep the private mapping inaccessible to reviewers.
6. Collect genuine independent reviews; disagreements retire/replace the row rather than being edited into agreement.
7. Finalize the reviewed holdout and seal it with `scripts/seal_v7_holdout.py`.
8. Archive/remove any prior default checkpoint, V7 result, and V7 evidence-verification receipt.
9. Run `python scripts/run_v7_preflight.py`; require exit 0.
10. Run `python scripts/run_v7_multilingual.py` **without `--resume`**. The runner will write both the V7 result and replay-verification receipt.
11. Independently rerun `python scripts/verify_v7_evidence.py` with a fresh `--output` path if a second integrity check is desired.
12. Run `python scripts/check_v8_unlock.py`; V8 remains locked unless it exits 0.
13. Only after V8 unlock should submission polish, final claims, screenshots, and demo metrics be frozen.

Never present a resumed run, provider-error run, unverified decision-only result, or synthetic review workflow as V7 qualification evidence.
