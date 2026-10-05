# AquaSignal v0.6.0 — sixth reliability campaign

## Executive summary

AquaSignal v0.6.0 completed a sixth reliability campaign focused on interaction failures that earlier campaigns under-covered rather than on adding product scope. The campaign preserved the deterministic SignalLock comparison core and concentrated on directive-boundary behavior, cross-directive relationship integrity, environmental-context containment, browser/request races, and release/package parity.

The campaign intentionally invalidated V16 after sealed semantics changed. A fresh V17 corpus was then authored, sealed before its exact cases were semantically executed, and executed once. V17 qualified on first execution.

Current release status:

- inherited SignalLock regressions: **611 / 611 passed**;
- AquaSignal-specific tests: **335 / 335 passed**;
- combined automated suite: **946 / 946 passed**;
- Aqua DEV: **14/14 unsafe BLOCK, 0 unsafe PASS, 10/10 clean PASS**;
- frozen V17: **73/73 expected decisions**;
- V17 unsafe/boundary: **47 total — 40 BLOCK, 4 REVIEW, 3 SOURCE_REVIEW, 0 PASS**;
- V17 clean: **26 / 26 PASS**;
- V17 evidence: **VERIFIED / QUALIFIED**.

These results describe the bounded prototype and its declared profile. They are not independent external validation or a safety/public-health certification.

## 1. Unpunctuated multi-item advisories

Earlier hardening made visual line wrapping semantically neutral, but a common copy/paste form remained awkward:

```text
- Do not swim in Stream A until 18:00
- Do not fish in Stream B until 19:00
```

Without terminal periods, the lines could merge into one unsupported directive. The repair is deliberately narrow: a newline becomes a directive boundary only when it introduces a recognized line-leading bullet/number marker. Ordinary wrapped lines inside a bullet still join. Evidence spans continue to refer to the original text, and unsupported second items remain fail-closed.

Regression coverage includes bullets, numbered lists, wrapped list items, and unsupported list-item additions.

## 2. Cross-directive relational rewiring

A deeper semantic failure class appears when all words/values are preserved globally but their relationships are changed:

```text
Source:
Do not swim in Stream A until 18:00.
Do not swim in Stream B until 19:00.

Candidate:
Do not swim in Stream A until 19:00.
Do not swim in Stream B until 18:00.
```

Set-level comparison can see the same action, sites, and times and still miss the reassignment. AquaSignal now adds a thin freshwater relational-binding invariant around the existing SignalLock engine. It confirms drift only when the global dimension multisets are preserved but the per-directive bindings differ.

Safe directive reordering remains PASS. Equivalent clock normalization combined with reordering remains PASS.

Additional generated checks exercised three-directive cyclic time/site permutations: safe three-clause reorder PASSed; cyclic reassignments BLOCKed.

V17 contains a dedicated `relational_rewire` critical family: **6/6 BLOCK**.

## 3. Environmental-context containment

The context-alignment layer previously handled the common case where a base-waterbody context (`Stream A`) supports a narrower advisory (`Stream A downstream of Bridge A`). A later hunt found the unsafe reverse could also MATCH: a context already narrowed to `Stream A downstream of Bridge A` could authorize an advisory broadened to all of `Stream A`.

The alignment rule is now directional:

- base-waterbody context -> same base or supported narrower upstream/downstream advisory: MATCH;
- relationally narrowed context -> exact same supported relation/landmark: MATCH;
- relationally narrowed context -> broader whole-waterbody advisory: MISMATCH;
- different waterbody/tributary/identifier: MISMATCH where the context inventory is complete.

This change is in the context/trust layer, not the V17-sealed semantic verifier. API-level regression proves `/authority` returns SOURCE_REVIEW for the broader-source case.

## 4. Conservative FHIR site identity

For environmental FHIR `Observation`, `subject.display` is not treated as verified Location identity because AquaSignal does not dereference that reference. A contradictory `reference=Location/stream-b` with `display=Stream A` therefore reports alignment UNKNOWN, not MATCH. A direct FHIR `Location` resource may still establish its own supported name.

This preserves provenance without overclaiming FHIR reference resolution or conformance.

## 5. SOURCE_REVIEW response minimization

The SOURCE_REVIEW error path previously echoed the parsed source contract even though the public UI did not need it. The response now returns only the review state, reasons, and context-alignment status. This reduces accidental advisory exposure in intermediaries/logs while preserving actionable review information.

## 6. Browser race hardening

Context imports were already last-request-wins. The sixth/post-seal hunt found a smaller authority-status race: a stale authority request could finish after the source changed and overwrite the new source status with `SOURCE REVIEW`. Verdict state was already invalidated, but the visible status could be misleading.

The authority failure UI update is now bound to the same source/context key that initiated the request. A stale response cannot overwrite status for newer input.

## 7. Static-asset freshness

Judge-facing `/`, `/app.js`, and `/app.css` now use `Cache-Control: no-cache` so browsers revalidate assets after deployment. API/evidence routes remain `no-store`. This avoids stale JS talking to a newer API after a rapid hackathon redeploy.

## 8. Concurrency and deterministic state

An in-process API concurrency sweep exercised:

- **120** parallel mixed verification calls using one frozen authority: **0 wrong verdicts**;
- **80** parallel context imports: **0 errors** and **80 distinct dataset hashes**;
- **32** concurrent release-evidence calls: all returned the same VERIFIED V17 result.

The qualified path remains stateless apart from the deployment secret and immutable package/evidence resources.

## 9. Production installed-wheel smoke

A clean v0.6.0 wheel was installed outside the source repository. From the installed package alone:

- `/` -> 200;
- `/api/aqua/health` -> 200;
- `/api/aqua/demo-context` -> 200;
- `/api/aqua/ready` -> 200 and reports v0.6.0 / V17;
- `/api/aqua/release-evidence` -> 200, VERIFIED V17;
- `/app.js` and `/app.css` -> 200 with revalidation cache policy.

A real Uvicorn production-mode smoke used a persistent 32+ byte secret and verified:

- context import/token;
- source authority;
- AFTER->BEFORE -> BLOCK;
- signed receipt verification;
- V17 release evidence;
- relational-context broadening -> SOURCE_REVIEW/MISMATCH.

After process restart with the same persistent secret, a previously minted authority token remained valid. Earlier campaigns already verify that changing the secret invalidates old trust tokens.

## 10. V17 frozen evidence

V16 was not refreshed after semantic changes; it was treated as stale/burned. V17 was authored fresh only after the sixth campaign stabilized.

### Frozen identity

- holdout: `aqua-holdout-v17`
- cases: **73**
- unsafe/boundary: **47**
- clean: **26**
- dataset SHA-256: `695dab284510502a6af26da611cc67d873f9ab1163d171b41b647282eed6d618`
- semantic fingerprint: `0d9e6c28bfaaa353443f692f000b15f6f1084737e7b824866c1d33f56bb15a06`
- evaluator fingerprint: `15c29f04756b2f9a20c3e5b2153358601d227386027fe2cb17d467a0922c8abc`
- requirements-lock SHA-256: `3ee3bc2a8ebc76d265bcdf4d9997b0f60630d0e678faa5b8820d6538f1f00fc3`
- Python: `3.13.5`
- sealed: `2026-10-04T09:02:40.475765+00:00`
- first execution: `2026-10-04T09:03:56.608315+00:00`

### First-execution result

- unsafe PASS: **0 / 47**;
- unsafe BLOCK: **40 / 47**;
- unsafe REVIEW: **4 / 47**;
- SOURCE_REVIEW: **3 / 47**;
- clean PASS: **26 / 26**;
- expected decisions: **73 / 73**;
- qualified: **yes**.

V17 is author-curated and is not described as independent external validation.

## 11. Freeze rule

Do not modify V17-sealed semantic/evaluator/runtime-lock dependencies before submission unless V17 is deliberately burned and a fresh holdout is created. Post-seal v0.6.0 changes were limited to unsealed context alignment, UI race handling, release packaging, and documentation.

## 12. Remaining declared limitations

- bounded deterministic English Freshwater Protective Communication Profile v1;
- unsupported/ambiguous language deliberately REVIEW/SOURCE_REVIEW;
- no autonomous environmental-risk inference;
- no autonomous publication authority;
- environmental FHIR import is a bounded R4 subset, not certification;
- context token proves server-bound imported bytes/metadata, not upstream dataset authenticity;
- HMAC receipts are server-verifiable, not public-key/non-repudiation records;
- frozen holdout is author-curated;
- Docker configuration exists, but Docker runtime should only be claimed if actually executed in a Docker-capable environment.
