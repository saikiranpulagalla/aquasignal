# SignalLock v0.6 — Next Actions

1. Export `SIGNALLOCK_TRUSTED_RUNTIME_SHA256=8d8dea2f85866e061e4623ac46b1cf261243741aab1cdc8b188c46992957e12d`.
2. Export the exact frozen `OPENAI_MODEL` and a real `OPENAI_API_KEY`.
3. Run `python scripts/fill_v7_authority_drafts.py`.
4. Complete human authority review and human Hindi/Telugu candidate authoring.
5. Run `python scripts/prepare_v7_blind_reviews.py data/multilingual/v7_authored.jsonl`.
6. Give reviewers only `v7_primary_review.jsonl` / `v7_secondary_review.jsonl`; keep `v7_blind_review_map.json` private.
7. Run `python scripts/finalize_v7_reviews.py ...` after both reviews are complete.
8. Seal with `python scripts/seal_v7_holdout.py data/multilingual/v7_reviewed.jsonl`.
9. Run `python scripts/run_v7_preflight.py`; it must exit 0.
10. Run `python scripts/run_v7_multilingual.py`; preserve the report even if the gate fails.

Do not fabricate human metadata or reuse a failed holdout after tuning.
