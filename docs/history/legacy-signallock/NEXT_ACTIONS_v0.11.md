# SignalLock v0.11 — Exact Next Actions

1. **Freeze this exact v0.11 package. Do not edit runtime code after human authoring starts.**
2. Externally record the package SHA-256 and runtime-tree SHA-256.
3. Set `SIGNALLOCK_TRUSTED_RUNTIME_SHA256` to the exact published runtime digest.
4. Set the exact frozen `OPENAI_MODEL` and a real `OPENAI_API_KEY`.
5. Before touching the holdout, run `python scripts/check_provider_retrieval_capability.py` on the non-holdout smoke input. It must prove the account/project permits response storage + later retrieval.
6. Generate/fill authority drafts and complete genuine human authority review.
7. Have independent humans author the Hindi/Telugu candidate cases from the fixed qualification plan.
8. Generate blinded primary/secondary review sheets and keep the private mapping inaccessible to reviewers.
9. Collect genuine independent reviews. A disagreement retires/replaces the case; do not edit it into agreement.
10. Finalize `data/multilingual/v7_reviewed.jsonl`.
11. Strictly seal the reviewed holdout under this exact v0.11 runtime/provider/model.
12. Remove/archive all prior default V7 checkpoint/result/replay/provider-verification files.
13. Run `python scripts/run_v7_preflight.py`; require exit 0.
14. Run `python scripts/run_v7_multilingual.py` **without `--resume`**.
15. Require 24/24 live executions, zero provider errors, zero checkpoint recovery, exact-model stored receipts, and all semantic thresholds passing.
16. Require `python scripts/verify_v7_evidence.py` to pass.
17. Require `python scripts/verify_v7_provider_evidence.py` to re-fetch and verify every provider response.
18. Run `python scripts/check_v8_unlock.py`; V8 remains locked unless it exits 0.
19. Archive the sealed holdout hash, manifest-file hash, result hash, replay receipt, provider-verification receipt, runtime digest, and package digest with submission evidence.

Do not present a resumed run, provider-error run, non-stored provider run, locally fabricated receipt, synthetic review workflow, or failed/reused holdout as V7 qualification evidence.
