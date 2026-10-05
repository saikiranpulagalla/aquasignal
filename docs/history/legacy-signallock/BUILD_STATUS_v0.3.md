# SignalLock AI v0.3 — Relational Hardening Build Status

## Promotion decision

**V0–V6: re-earned on offline/controlled evidence.**

**V7: implementation hardened, but live multilingual qualification remains BLOCKED until a genuinely independent reviewed Hindi/Telugu holdout is sealed and executed with the real provider credentials.**

No production-safety or autonomous-publication claim is made.

## Verified locally

- Automated tests: **143 / 143 PASS**
- Controlled DEV benchmark: **108 cases**
  - unsafe: **76**, unsafe PASS: **0**, BLOCK: **76**
  - clean: **32**, clean PASS: **32**, BLOCK: **0**
  - Critical Unsafe Pass Rate: **0%**
  - clean PASS rate: **100%**
- Post-repair forensic audit: **PASS**
  - 13/13 previously known unsafe text attacks intercepted
  - 10/10 safe text rewrites PASS
  - 15/15 contract-semantic corruptions do not PASS
- Second-order adversarial audit: **PASS**
  - 12/12 relational/deontic/logic unsafe attacks BLOCK
  - 4/4 targeted safe relational paraphrases PASS
  - 0/7 material CAP mutations PASS
  - forged client authority: HTTP 422
  - false Hindi canonical semantics with exact native quote: REVIEW, not PASS
  - numeric-only/gamed V7 metrics: gate FAIL
  - mislabeled English-as-Hindi/Telugu holdout: strict sealer REFUSED
  - V7 preflight not ready: process exits non-zero

## Architectural repairs

1. Flat fact-set matching replaced with one-to-one **scoped directive** matching while retaining legacy fields for compatibility.
2. Modality, scoped audience/area, temporal operator, bound quantity/exception, order and AND/OR logic are preserved per action.
3. Unicode dash/zero-width lexical normalization preserves original evidence offsets.
4. Source authority is server sealed with an HMAC over source hash + canonical contract; legacy heuristic clients are independently re-derived.
5. Whole-message CAP verification compares envelope, every info block and geospatial targets under strict CAP profile parsing.
6. Live multilingual extraction has exact provenance plus an independent native semantic contradiction guard; unresolved critical semantics become REVIEW.
7. Public live-provider endpoints are fail-closed unless a demo token is configured and are rate limited.
8. Browser verification uses request-generation/state snapshots so a slow old verdict cannot be rendered against edited text.
9. V7 strict sealing validates language script, reviewer metadata, second review for unsafe rows, duplicate/near-duplicate padding, source/candidate diversity and required fault-class coverage.
10. V7 seals provider/model/config/prompt/schema fingerprints and supports either clean Git identity or a packaged release tree hash.
11. V7 execution uses bounded retries, per-case checkpoint/resume, counts terminal provider failures as REVIEW, and exits non-zero when the gate fails.

## Remaining external qualification

The code path is ready for the next gate, but the following are intentionally **not claimed as complete** in this environment:

- real OpenAI Hindi/Telugu holdout execution (no user credentials were supplied to this build session);
- independently human-reviewed final V7 holdout with the required reviewer/fault metadata;
- broader real-world CAP corpus beyond the controlled fixtures.

These are qualification dependencies, not silently simulated results.
