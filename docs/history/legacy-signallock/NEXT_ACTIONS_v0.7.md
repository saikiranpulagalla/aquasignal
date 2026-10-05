# SignalLock v0.7 — Next Actions

1. Freeze this v0.7 package and publish/record its runtime SHA-256.
2. Set `SIGNALLOCK_TRUSTED_RUNTIME_SHA256` to that exact externally recorded runtime digest.
3. Set the exact frozen `OPENAI_MODEL` and a real `OPENAI_API_KEY`.
4. Populate source-contract drafts with `python scripts/fill_v7_authority_drafts.py`.
5. Complete genuine human authority review and human Hindi/Telugu candidate authoring.
6. Generate blinded reviews with `python scripts/prepare_v7_blind_reviews.py <authored-packet>` and keep the private mapping private.
7. Collect independent primary + secondary human reviews; do not edit disagreements into agreement.
8. Finalize with `python scripts/finalize_v7_reviews.py ...`.
9. Seal with `python scripts/seal_v7_holdout.py data/multilingual/v7_reviewed.jsonl`.
10. Ensure the default V7 checkpoint/result paths do not contain evidence from an earlier run; archive them if they do.
11. Run `python scripts/run_v7_preflight.py`; it must exit 0.
12. Run `python scripts/run_v7_multilingual.py` **without `--resume`** for certification.
13. V7 can pass only if all 24 cases execute live, provider errors are 0, checkpoint-recovered cases are 0, and all semantic gates pass.

`--resume` exists only to recover diagnostic information after interruption. A resumed run is intentionally non-qualifying and must never be presented as V7 certification evidence.
