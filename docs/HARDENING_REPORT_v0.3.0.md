# AquaSignal v0.3.0 — third reliability campaign

## Purpose

This campaign started from the hardened v0.2.0 artifact and deliberately targeted reliability classes that prior audits had not exercised deeply enough. The goal was not feature growth; it was to find inconsistencies between parser layers, API/schema boundaries, provenance adapters, shipped package resources, streaming request behavior, and the frozen-evidence process without weakening the already-qualified verifier.

## Final release status

- inherited SignalLock regression boundary: **611/611 passing**;
- AquaSignal-specific automated tests: **214/214 passing**;
- combined automated suite: **825/825 passing**;
- Aqua DEV: **14/14 unsafe BLOCK, 0 unsafe PASS, 10/10 clean PASS**;
- frozen author-curated holdout V13: **103/103 expected decisions**;
- V13 unsafe/boundary: **63 total — 52 BLOCK, 5 REVIEW, 6 SOURCE_REVIEW, 0 PASS**;
- V13 clean: **40/40 PASS**;
- V13 release evidence: **VERIFIED / QUALIFIED**.

These are bounded prototype results, not safety certification or independent external validation.

## New failure classes found and fixed

### 1. Strict API schemas

Public request models previously ignored unknown top-level keys. That could make a misspelled safety-critical field look accepted. Public Aqua request models now use `extra="forbid"`; regressions cover context import, authority, and verification requests.

### 2. FHIR structural complexity and non-finite JSON

The bounded environmental FHIR adapter now rejects excessive nesting/node counts and `NaN`/`Infinity` values before canonicalization. This prevents irrelevant deeply nested input from becoming a parser/resource-exhaustion path and keeps accepted JSON inside the intended standards boundary.

### 3. Validation-error Unicode crash

A lone Unicode surrogate in an invalid request could be rejected by Pydantic but then crash FastAPI while echoing the raw invalid value in the 422 response. AquaSignal now emits sanitized validation details without raw invalid input. Malformed Unicode produces controlled 422 responses instead of 500s.

### 4. Forged deep context before HMAC verification

A client-submitted forged `raw_summary` could previously be nested deeply enough to fail during canonical hashing before the invalid context token was rejected. `AquaContext` now bounds raw-summary depth, node count, list size, key/string size, and non-finite numbers at schema validation.

### 5. CSV metadata-column order dependency

A CSV containing both `time` and `date` could choose whichever appeared first, rejecting a valid export if bare `time` preceded the ISO date. Metadata selection now uses explicit semantic priority (`datetime/timestamp/observed-at/date` before bare `time`) independent of header order.

### 6. Chunked/no-Content-Length request size bypass

The request-size middleware previously relied primarily on `Content-Length`. Streaming/chunked bodies without that header are now bounded while streaming, before Pydantic materializes them. Oversized streaming requests return 413 with the same security/no-store headers as ordinary API responses.

### 7. Source/package resource-root ambiguity

Installed-wheel resource discovery could mistake an unrelated sibling `data/` or `web_aqua/` directory for a source checkout. Source mode now requires explicit source-tree markers; otherwise package resources are used.

### 8. Readiness vs liveness

`/api/aqua/health` proves that the process is alive. New `/api/aqua/ready` separately proves that required runtime assets are present and frozen release evidence recomputes as verified. Docker health checking now targets readiness. Public readiness failures use stable resource labels rather than leaking host filesystem paths.

### 9. Abbreviated proper-name sentence splitting

The profile's place grammar allowed internal periods, but sentence splitting treated `River St. John` / `River Mt. Hope` as sentence boundaries. The splitter now preserves the supported `St.`/`Mt.` proper-name abbreviations while regressions prove that a real boundary such as `Site A. Keep children ...` still splits correctly.

### 10. Metamorphic grammar regression

A permanent property-style regression now checks identity across a matrix of supported actions/places/times and one-slot safety mutations. During the campaign an additional generated sweep exercised 289 supported identity cases and 197 safety mutations with zero unsafe PASS; the durable test prevents future changes from silently reopening those dimensions.

## A proposed fix that was deliberately rolled back

The campaign initially considered treating the word `direct` in `avoid direct contact` as a separate safety invariant. Full-suite testing showed that this would conflict with an already-qualified V1 equivalence: `avoid direct contact`, `avoid contact with water`, and `do not touch water` intentionally represent the same physical-contact prohibition in this profile. The tightening was rolled back rather than forcing the tests to accommodate a semantic overreach. This is an example of using regression evidence to prevent a fix from creating a false-BLOCK class.

## Frozen evidence discipline

The existing V12 artifact was not refreshed. Changes to sealed semantic/evaluator dependencies made it stale, so V12 was treated as burned.

A fresh **V13** corpus was authored with fresh site names/times and new proper-name-abbreviation controls. It was schema-validated only, then sealed to:

- dataset SHA-256;
- semantic dependency fingerprint;
- evaluator fingerprint;
- `requirements.lock` SHA-256;
- Python runtime version.

Only after sealing was it executed once.

### V13 identity

- dataset SHA-256: `629b8dcf9ff729dc7b3b89c60528744c46e302ddd9d7cef31cda6047aebd72b0`
- semantic fingerprint: `761e1fb44ffb322f3d935df5fc96ae054dd97ab18513c937ba012dce5af42015`
- evaluator fingerprint: `cb4bb74c1b4dc7ac01584c39398f57609c7cf591b871a0a28249a97e2a9caf42`
- runtime lock SHA-256: `3ee3bc2a8ebc76d265bcdf4d9997b0f60630d0e678faa5b8820d6538f1f00fc3`
- Python: `3.13.5`

V13 passed on its first execution: 103/103 declared expectations, 0 unsafe PASS, and 40/40 clean PASS.

## Shipped-artifact verification

A clean v0.3.0 wheel was built with package-resource synchronization. It was installed outside the source repository and independently verified to serve:

- `/` → 200;
- `/api/aqua/health` → 200;
- `/api/aqua/ready` → 200;
- `/api/aqua/demo-context` → 200;
- `/api/aqua/release-evidence` → 200 / V13 VERIFIED.

Wheel inspection confirmed that packaged frozen-evidence resources are V13 only; stale packaged holdout resources are removed by the synchronization/build step.

A real production-mode Uvicorn process was also started from the installed package with a persistent 32+ byte authority secret. Source authority, AFTER→BEFORE verification, signed receipt verification, readiness, and restrictive API security/cache headers behaved correctly.

## Remaining declared limitations

- V13 is author-curated, not independent external validation.
- The deterministic automatic-verdict profile is intentionally bounded English V1; unsupported meaning fails closed rather than being guessed.
- Context import proves what bytes this AquaSignal server imported and bound; it does not independently authenticate the upstream OneAquaHealth source.
- HMAC receipts are server-verifiable integrity records, not third-party/nonrepudiation signatures.
- Revision is cryptographically bound but the standalone prototype is not a global revision-supersession registry.
- Environmental FHIR import is a bounded interoperability adapter and does not claim FHIR/OAH certification.
- Docker configuration is present; if the execution environment has no Docker daemon, Docker execution must remain disclosed as unverified.

## Release recommendation

Freeze the V13 semantic/evaluator dependency set. Do not add features before submission. Remaining work should be publication, deployed-environment smoke testing, screenshots/video, Devpost/Q&A polish, and—if feasible without altering the frozen release—external human review of the project and evaluation framing.
