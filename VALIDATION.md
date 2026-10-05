# AquaSignal validation and qualification evidence

This document describes the evidence for the **AquaSignal v0.6.1** hackathon/research prototype. It is not a safety certification, public-health validation, FHIR certification, or guarantee of complete language coverage.

## Current release gate

| Evidence | Result |
|---|---:|
| Inherited SignalLock unit/integration/regression | **611 / 611 passed** |
| AquaSignal-specific tests | **351 collected; final qualified execution pending** |
| Combined automated suite | **962 collected; final qualified execution pending** |
| Aqua DEV benchmark | **24 / 24 expected decisions met** |
| Frozen release holdout | **Aqua holdout V17 — VERIFIED / QUALIFIED** |

The inherited 611-test SignalLock suite is a regression boundary for reused infrastructure. It is **not** relabeled as freshwater validation.

## Aqua DEV benchmark

Developer-visible cases used during implementation:

- total: **24**
- unsafe: **14**
- unsafe `PASS`: **0**
- unsafe `BLOCK`: **14**
- clean/equivalent: **10**
- clean `PASS`: **10**
- clean `BLOCK`: **0**
- expectation failures: **0**

This corpus is intentionally a regression/development set, not a holdout.

## Frozen Aqua holdout V17 — current release evidence

V17 is an **author-curated frozen release holdout**, not independent external validation. The exact cases were not executed before sealing.

### Sealed identity

- holdout: `aqua-holdout-v17`
- cases: **73**
- unsafe/boundary cases: **47**
- clean cases: **26**
- dataset SHA-256: `695dab284510502a6af26da611cc67d873f9ab1163d171b41b647282eed6d618`
- semantic fingerprint: `0d9e6c28bfaaa353443f692f000b15f6f1084737e7b824866c1d33f56bb15a06`
- evaluator fingerprint: `15c29f04756b2f9a20c3e5b2153358601d227386027fe2cb17d467a0922c8abc`
- requirements-lock SHA-256: `3ee3bc2a8ebc76d265bcdf4d9997b0f60630d0e678faa5b8820d6538f1f00fc3`
- sealed Python runtime: **3.13.5**
- sealed: `2026-10-04T09:02:40.475765+00:00`
- first execution: `2026-10-04T09:03:56.608315+00:00`

### V17 result

| Metric | Result |
|---|---:|
| Unsafe PASS | **0 / 47** |
| Unsafe BLOCK | **40 / 47** |
| Unsafe REVIEW | **4 / 47** |
| Unsafe SOURCE_REVIEW | **3 / 47** |
| Clean PASS | **26 / 26** |
| Clean REVIEW | **0 / 26** |
| Clean BLOCK | **0 / 26** |
| Expected decisions met | **73 / 73** |

The declared critical mutation families are required to `BLOCK`. V17 adds a dedicated **relational_rewire** family; all six V17 relational-rewire cases `BLOCK`. Boundary cases intentionally test fail-closed behavior: unsupported candidates may `REVIEW`, and unsupported authoritative sources may `SOURCE_REVIEW`.

### Release gates

V17 qualifies only if all of the following remain true:

- unsafe `PASS` = **0**;
- clean PASS rate ≥ **80%**;
- clean BLOCK rate ≤ **5%**;
- every frozen case meets its declared expected decision;
- every declared critical mutation family is present and **100% BLOCK**;
- dataset hash matches the sealed manifest;
- semantic dependency fingerprint matches;
- evaluator fingerprint matches;
- exact runtime-lock hash matches;
- Python runtime version matches;
- saved result exactly matches full case-by-case recomputation.

`GET /api/aqua/release-evidence`, `scripts/verify_aqua_holdout.py`, and `scripts/release_gate.py` recompute V17 rather than trusting a stored headline metric.

## Why earlier evidence was burned

AquaSignal preserves failed/stale evidence instead of rewriting history.

### V1 — semantic defect found

The first frozen holdout exposed an unsafe PASS:

```text
Source:    Do not fish in River C until 20:00.
Candidate: Do not fish or swim in River C until 20:00.
```

Root cause: the direct-prohibition parser handled supported coordinated verbs asymmetrically. The parser was repaired generically, regressions were added, and V1 remained burned.

### V15 — fifth reliability campaign changed sealed semantics

V15 qualified under the v0.4.0 semantic boundary, but the fifth reliability campaign intentionally changed sealed parser semantics; V15 was burned rather than refreshed. V16 was authored after that campaign and qualified. The sixth reliability campaign then changed sealed semantics again to make unpunctuated list-item boundaries reliable and to detect cross-directive relational rewiring. V16 therefore became stale and was burned. V17 was authored only after the sixth campaign stabilized.

### V14 — broader Unicode property sweep found a new identity collision

V14 passed its frozen corpus, but a later property-style sweep over Unicode compatibility characters found that `Site ϴ` and `Site Θ` still collapsed through ordinary Unicode lowercasing. V14 was therefore burned. Identifier normalization was changed to preserve compatibility characters while retaining ordinary case and canonical-accent equivalence. The repaired rule was checked across **2,690** compatibility-distinct Unicode word characters with **0 collisions** before V15 was authored.

### V10 — post-seal integrity violation detected

V10 initially produced a qualifying result, but the dataset later differed from its sealed SHA-256/case count. The evidence verifier correctly marked the release evidence stale. V10 was **not resealed in place** and is not current release evidence.

This distinction matters: a holdout is useful only if both model behavior and evidence integrity are preserved.

## Hardening after the first red-team

The hardening campaigns through v0.6.1 added/fixed, among other things:

- full-sentence fail-closed qualification rather than “one recognized phrase means represented”;
- unsupported conditions, exceptions, extra actions, time expressions, and place qualifiers cannot hide behind a partial match;
- coordinated direct-prohibition parsing;
- `must`/`should`/`may`/`can` force weakening detection;
- explicit positive-permission and negated-avoid reversal handling;
- upstream/downstream semantic contradiction policy;
- exact/multiword/Unicode waterbody identity handling;
- clock validity and clock-format equivalence;
- minute/hour/second duration normalization and conversion;
- non-positive protective quantities fail source readiness;
- conservative Source Readiness Gate for unsupported authoritative language;
- server-minted context tokens before authority signing;
- compact source/context/contract-hash-bound authority tokens;
- canonical base64url token validation;
- signed HMAC integrity receipts binding source and candidate contract hashes;
- persistent production-secret requirement with explicit development-only ephemeral mode;
- bounded CSV/FHIR parsing, including controlled oversized CSV-field failure;
- wheel/package resource support for UI, demo context, runtime lock, and frozen evidence;
- exact dependency locks used by CI/Docker configuration.

## Additional adversarial evidence

Before final freeze, generated/metamorphic sweeps were used as development evidence, not as an independent holdout:

- **112 / 112** additional in-profile unsafe mutations BLOCKed in the first deep red-team sweep;
- **46 / 46** clean in-profile equivalents PASSed in that sweep;
- a later generated sweep produced **49 unsafe transformations with 0 PASS** and **11/11 clean equivalents PASS**;
- a larger metamorphic comparison sweep covered **1,648 expectations with 0 mismatches** across supported prohibition aliases, clock equivalence, site changes, force weakening, and contact/touch paraphrases.

These generated checks are useful regression evidence but are not substituted for independent external validation.

## Trust and provenance scope

AquaSignal proves that a server-imported context object, source contract, source text, advisory identity/revision, and candidate verification are cryptographically bound within the running deployment.

It does **not** prove that an uploaded CSV was genuinely exported by OneAquaHealth. The Resilience-compatible CSV adapter provides provenance/binding to the uploaded bytes, not upstream authenticity certification.

FHIR import accepts a bounded environmental `Observation`/`Location` subset. Exact configured OAH profile URIs may be recognized, but AquaSignal does **not** claim FHIR certification or full OneAquaHealth IG conformance.

Integrity receipts use HMAC-SHA256. They are **server-verifiable**, not public-key/nonrepudiation attestations.

## Packaging/runtime checks

Verified in the audit environment:

- source-tree full test suite;
- release gate and V15 recomputation;
- JavaScript syntax check;
- offline wheel build using the installed build toolchain (`--no-build-isolation`);
- wheel installation into an isolated target outside the repository;
- installed-wheel `GET /`, `/api/aqua/health`, `/api/aqua/demo-context`, and `/api/aqua/release-evidence` all returned HTTP 200;
- malformed FHIR/CSV/trust-boundary operational fuzz produced no uncontrolled HTTP 5xx after hardening;
- optional paid AI rewrite endpoint is disabled by default.

Docker execution remains **unverified** in this environment because Docker is unavailable.

## Known limits

- automatic PASS is bounded to the declared English Freshwater Protective Communication Profile v1;
- unsupported/ambiguous operational language is intentionally conservative;
- arbitrary natural-language geography/conditions/exceptions are not claimed;
- OAH/Resilience context is provenance, not ecological/public-health risk inference;
- the V17 holdout is author-curated, not independent external evaluation;
- production deployment requires a persistent `AQUASIGNAL_AUTHORITY_SECRET` of at least 32 bytes;
- broader language, independent domain review, operational governance, and deployment qualification remain required before real-world safety use.

## Fifth reliability campaign (v0.5.0)

The fifth campaign specifically targeted failure classes that earlier semantic hunts under-covered: visual line wraps/list decoration, environmental-FHIR privacy boundaries, raw FHIR/CSV byte provenance, browser context-import races, non-JSON proxy failures, extreme ISO timestamps, known FHIR R4 status codes, cross-protocol token replay, deeply nested JSON decoder exhaustion, and whitespace/confusable metamorphic behavior. See `docs/HARDENING_REPORT_v0.5.0.md`.

V15 was burned because the visual-layout repair changed a sealed semantic dependency. V16 was authored only after these changes stabilized and passed on first execution with **0/46 unsafe PASS and 30/30 clean PASS**.

## Sixth reliability campaign (v0.6.0)

See `docs/HARDENING_REPORT_v0.6.0.md` for the detailed campaign report.

The sixth campaign targeted previously under-tested interactions rather than adding product scope: unpunctuated multi-item advisories, cross-directive time/site/audience rebinding, conservative FHIR Observation alignment, SOURCE_REVIEW response minimization, static asset freshness, three-directive cyclic reassignments, parallel verification/import behavior, relational environmental-context narrowing, and stale browser authority responses.

Key results after the campaign:

- full automated suite: **946 / 946 passed**;
- Aqua-specific tests: **335 / 335 passed**;
- DEV: **14/14 unsafe BLOCK, 0 unsafe PASS, 10/10 clean PASS**;
- V17: **0/47 unsafe PASS, 40 BLOCK, 4 REVIEW, 3 SOURCE_REVIEW, 26/26 clean PASS**;
- generated three-directive cyclic time/site reassignments `BLOCK` while safe three-clause reorder remains `PASS`;
- 120 parallel mixed verifications produced zero wrong verdicts; 80 parallel context imports produced zero errors and distinct hashes;
- installed-wheel production smoke, signed-receipt verification, restart continuity with a persistent secret, and V17 evidence recomputation all passed.

Post-seal fixes were limited to **unsealed operational/context/UI layers**. V17's sealed semantic/evaluator files were not changed.


## Seventh reliability campaign (v0.6.1)

This patch-level campaign intentionally left the V17 semantic/evaluator dependency set unchanged. It targeted operational, provenance, transport, and deployment failure classes not covered deeply enough by the earlier campaigns.

Verified/fixed in this campaign:

- exact source and candidate text are preserved for authority/receipt SHA-256 binding; whitespace is used only to test emptiness, not silently stripped from provenance;
- Resilience-compatible CSV imports reject conflicting populated date/datetime aliases while allowing equivalent offset timestamps;
- sparse timestamp columns use row-wise date fallback so provenance ranges do not silently omit rows;
- time-of-day-only CSV metadata is accepted without inventing a calendar date range;
- extreme JSON integer literals are converted to controlled `422` responses with API `no-store` and security headers rather than escaping middleware as `500`;
- real read-only runtime under an unprivileged user serves health, readiness, UI, and release-evidence endpoints;
- timezone changes (UTC, Asia/Kolkata, America/New_York, Pacific/Kiritimati) do not change canonical context binding or V17 verification;
- malformed-request privacy testing found no advisory marker leakage into validation responses or Uvicorn access logs;
- max-shape timing checks remained bounded (20,000-row CSV ~0.1 s in the audit environment; near-8,000-character unsupported advisory ~0.003 s);
- conditional/range static responses preserve security headers; API method errors remain `no-store`;
- malformed JSON transport matrix (duplicate keys, invalid UTF-8, deep nesting, huge integers, NaN/Infinity-like values, huge exponents) produced no uncontrolled 5xx after hardening.

Two proposed changes were deliberately **not** shipped because the full release discipline showed they weakened stronger guarantees:

- CR-only list-line parsing would require changing a V17-sealed semantic file for a low-severity fail-closed usability edge, so the parser remains conservative and V17 remains valid;
- broadening `Requires-Python` beyond exact `3.13.5` was rolled back because other patch runtimes were not actually qualified.

V17 therefore remains the current frozen semantic evidence for v0.6.1.
