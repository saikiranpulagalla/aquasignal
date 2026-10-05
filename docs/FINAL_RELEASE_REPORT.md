# AquaSignal v0.6.1 — release report

## Identity

- Product: **AquaSignal — Verified Freshwater Risk Communication**
- Hackathon: OneAquaHealth IEEE Global Hackathon 2026
- Primary track: **Track 6 — Resilience Informatics**
- Version: `0.6.1`
- Semantic profile: `freshwater-protective-communication-v1`
- Current frozen evidence: `aqua-holdout-v17`
- Dataset SHA-256: `695dab284510502a6af26da611cc67d873f9ab1163d171b41b647282eed6d618`
- Semantic fingerprint: `0d9e6c28bfaaa353443f692f000b15f6f1084737e7b824866c1d33f56bb15a06`
- Evaluator fingerprint: `15c29f04756b2f9a20c3e5b2153358601d227386027fe2cb17d467a0922c8abc`
- Runtime lock SHA-256: `3ee3bc2a8ebc76d265bcdf4d9997b0f60630d0e678faa5b8820d6538f1f00fc3`
- Sealed Python: `3.13.5`
- Source commit: pending public Git commit; regenerate `RELEASE_MANIFEST.json` after commit if desired.

## Release gates

- inherited SignalLock: **611 / 611 passed**
- AquaSignal-specific: **351 collected; final qualified execution pending**
- combined: **962 collected; final qualified execution pending**
- DEV: **14/14 unsafe BLOCK, 0 unsafe PASS, 10/10 clean PASS**
- frozen V17: **73/73 expected decisions**
  - unsafe/boundary: **47 — 40 BLOCK, 4 REVIEW, 3 SOURCE_REVIEW, 0 PASS**
  - clean: **26/26 PASS, 0 REVIEW, 0 BLOCK**
- release evidence: **VERIFIED / QUALIFIED**

V17 is author-curated, not independent external validation. It was sealed before its exact cases were semantically executed and was executed once. The release-evidence path recomputes all cases and checks dataset, semantic, evaluator, runtime-lock, Python-version, saved-result, arithmetic, expected-decision, and critical-family bindings.

## Sixth reliability campaign

The sixth campaign added no product scope. It targeted failure interactions missed by earlier campaigns:

- unpunctuated bullet/numbered directives while preserving wrapped-line equivalence;
- cross-directive relational rewiring (same global words/values, wrong site/time/audience bindings);
- safe multi-directive reorder controls;
- conservative FHIR Observation site alignment;
- SOURCE_REVIEW response minimization;
- static-asset freshness after deployment;
- relational context containment (a context bound downstream of a landmark cannot authorize a whole-waterbody advisory);
- stale browser authority-response races;
- three-directive cyclic time/site swaps;
- parallel verification and parallel context imports.

V16 was burned when sealed semantic dependencies changed during this campaign. V17 was created fresh only after those changes stabilized.


## Seventh reliability campaign

The v0.6.1 patch-level campaign did not change V17-sealed semantics. It hardened exact source/candidate provenance binding, CSV temporal metadata consistency/fallback, time-only CSV imports, hostile JSON integer handling, read-only runtime behavior, environment determinism, validation/log privacy, and resource-bound behavior. Proposed CR-only semantic expansion and broader Python compatibility were intentionally rolled back because they would weaken stronger release guarantees without sufficient qualification evidence. See `docs/HARDENING_REPORT_v0.6.1.md`.

## Production/package verification

Verified on the final v0.6.1 tree:

- source-tree `scripts/release_gate.py` → PASS;
- clean wheel build with `--no-build-isolation` → PASS;
- installed wheel outside the source repository serves `/`, health, demo context, readiness, static assets, and V17 release evidence;
- installed wheel contains **only V17 runtime evidence**;
- real production-mode HTTP smoke with a persistent 32+ byte secret passed authority→verify→signed receipt, V17 evidence, and relational-context mismatch handling;
- an authority token minted before process restart remained valid after restart with the same persistent secret;
- 120 parallel mixed verification requests produced zero wrong verdicts;
- 80 parallel context imports produced zero errors and 80 distinct dataset hashes;
- 32 concurrent release-evidence requests returned the same VERIFIED V17 result.

Docker configuration is present, but Docker execution is not claimed unless run in an environment with a Docker daemon.

## Trust boundaries

- environmental context must be server-imported and receives a signed context token;
- Source Readiness refuses unsupported/conflicting authoritative language;
- authority tokens bind source text/contract, context, advisory identity, revision, profile, and engine version;
- AI may propose wording but has no PASS/BLOCK authority;
- deterministic freshwater extraction + semantic policy + SignalLock comparison produce the qualified verdict path;
- receipts are HMAC server-verifiable records, not public-key attestations;
- FHIR support is a bounded environmental R4-subset import, not FHIR certification;
- AquaSignal does not infer whether water is dangerous and does not replace environmental/public-health authority.

## Limits

AquaSignal remains a hackathon/research prototype. V17 is author-curated. Real-world deployment requires independent ecological/communication review, larger external qualification sets, governance, operational monitoring, and deployment-specific security controls.
