# AquaSignal v0.2.0 — adversarial hardening report

## Executive result

AquaSignal v0.2.0 is the hardened successor to the initial v0.1.0 release candidate. The work deliberately prioritized fail-closed semantics, evidence integrity, provenance binding, packaging reproducibility, and production behavior over new features.

Current verified state:

- **611/611** inherited SignalLock tests pass;
- **176/176** AquaSignal-specific tests pass;
- **787/787** combined tests pass;
- Aqua DEV: **14/14 unsafe BLOCK, 0 unsafe PASS, 10/10 clean PASS**;
- frozen V11 holdout: **93/93 expected decisions**, including **0/56 unsafe PASS** and **37/37 clean PASS**;
- production-mode Uvicorn smoke passes;
- same-secret restart/cross-process tokens survive; different-secret tokens fail;
- wheel build/install/runtime smoke passes using the pinned local build toolchain;
- V11 resource identity in the wheel is clean and contains no stale packaged holdout data.

This remains a bounded hackathon/research prototype, not a safety certification or public-health authority.

## Repair philosophy

The hardening work followed four rules:

1. **Reproduce first.** Every confirmed defect was converted into a regression or deterministic reproduction before changing behavior.
2. **Fix the boundary, not the example.** Changes were implemented as grammar/policy/trust-boundary rules rather than one-off string exceptions.
3. **Protect the stable comparator.** The inherited SignalLock comparison engine was left intact unless an inherited regression demonstrated a core defect.
4. **Burn evidence instead of refreshing it.** If a sealed holdout exposed a defect or a relevant post-seal change occurred, that holdout version was treated as historical/burned and a new version was created.

## Major semantic failures found and fixed

### 1. Partial sentence coverage could produce unsafe PASS

**Failure:** once one supported action was recognized, unsupported operational meaning in the same sentence could disappear without marking the sentence unresolved.

Examples included:

- `Do not swim or kayak ...` → candidate dropped `kayak`;
- conditions/exceptions disappearing;
- additional short commands such as `Wear gloves.` or `Call 911.`;
- unsupported time/place qualifiers.

**Repair:** automatic PASS now requires the full directive to fit the declared deterministic freshwater grammar. Partial structured evidence may still be extracted, but unresolved operational residue fails closed to `REVIEW`/`SOURCE_REVIEW`.

### 2. Modality and polarity weakening

**Failure:** variants such as `must avoid` → `may avoid`, `can avoid`, or explicit permission/reversal constructions could collapse into the same prohibition representation.

**Repair:** freshwater force/polarity policy now independently tracks strong prohibition, weakening, positive permission and negated-avoid reversal. Supported decisive reversals BLOCK even when clock formatting changes simultaneously.

### 3. Coordinated action asymmetry

**Failure:** the first frozen holdout exposed `Do not fish` → `Do not fish or swim` as an unsafe PASS.

**Repair:** supported OR-coordinated direct prohibitions are parsed symmetrically across the supported action family. Negative AND scope remains conservative/fail-closed rather than being guessed equivalent.

### 4. Place-scope ambiguity and clause swallowing

**Failure:** site extraction could absorb later operational clauses into a place name; direction words inside real proper names could also be over-blocked.

**Repair:** reserved operational connectors stop place capture; supported proper names such as `River North`/`Bridge North` remain valid. Exact waterbody identifiers are preserved, including single-letter and multiword names.

### 5. Freshwater relative direction

**Failure:** the generic verifier knew compass opposites but not the domain contradiction `upstream` ↔ `downstream`.

**Repair:** Aqua semantic policy explicitly models supported flow-direction contradiction while leaving broader unsupported spatial language fail-closed.

### 6. Invalid/ambiguous temporal and quantity forms

**Failures included:**

- invalid clocks such as `99:99` qualifying syntactically;
- non-positive boil durations;
- `mins`/`hrs` aliases not normalizing consistently;
- equivalent hour/minute/second quantities false-BLOCKing.

**Repair:** valid-clock checks, specific quantity semantics, unit aliases and deterministic time-unit conversion were added. Safe equivalents such as `1 hour` ↔ `60 minutes` and common clock forms remain PASS-capable.

## Source-readiness hardening

The original trust model could cryptographically bind a source contract even when the source itself was not fully representable.

The hardened flow is:

`source → deterministic freshwater extraction → Source Readiness → authority token`

If operational meaning is unsupported, contradictory, non-positive, malformed or otherwise unresolved, AquaSignal refuses to mint a clean automatic authority state and returns `SOURCE_REVIEW`.

## Context/provenance hardening

### Server-minted context token

The original API could accept a client-constructed context object directly into authority creation. That provided binding but not evidence that the context passed through the import policy.

Now CSV/FHIR import mints a signed context token. Authority creation requires that token and re-verifies it against the exact context object.

### Compact authority token

Large contracts/context previously produced authority tokens that could exceed the verify endpoint's own token limit.

The current authority token carries compact hashes/identity rather than embedding the entire contract/context body. It binds source, contract, context, advisory ID, revision, profile and engine identity.

### Canonical token encoding

Token parsing now rejects invalid characters and non-canonical Base64URL encodings, including alternate pad-bit spellings that decode to the same bytes.

### Production secret lifecycle

- development may use an explicitly reported ephemeral secret;
- `AQUASIGNAL_ENV=production` refuses startup without a configured secret;
- configured secrets must be at least 32 bytes;
- same-secret restart/cross-process verification was executed successfully;
- old tokens were rejected under a different secret.

### Context alignment

A final live smoke found that context `Stream A` was initially considered different from advisory scope `Stream A downstream of Bridge A`.

The corrected policy matches the **exact base waterbody** plus a supported upstream/downstream suffix. It deliberately does not use loose prefix matching, so `Stream A` does not match `Stream B` or `Stream AB`.

### CSV date quality

The final malformed-input hunt found that a declared date field containing `not-a-date` was accepted as provenance metadata. CSV context import now requires nonblank declared date/time values to be ISO-8601-compatible while accepting ordinary ISO dates and offset datetimes.

## FHIR/adapter hardening

The environmental FHIR path is intentionally bounded:

- only environmental `Observation`/`Location` resources are accepted in V1;
- malformed shapes return controlled 4xx responses rather than 5xx crashes;
- configured exact OAH profile URIs may be recognized, but no FHIR/OAH certification is claimed;
- no arbitrary remote URL fetch is implemented;
- patient resources remain out of scope.

CSV/FHIR adapters also enforce size/row/column/header/resource bounds.

## Integrity receipt hardening

Receipts are now HMAC-signed and self-verifiable by the deployment. The signature serialization was specifically regression-tested after a UTC datetime round-trip bug was found during the second hunt.

Receipts bind source/candidate hashes and typed contract hashes. They are **server-verifiable HMAC records**, not public-key/nonrepudiation attestations.

## Release-evidence hardening

The initial release evidence could become stale without detection because not every semantic dependency was sealed and stored summary arithmetic was not fully recomputed.

V11 now verifies/recomputes:

- dataset SHA-256;
- semantic dependency fingerprint;
- evaluator dependency fingerprint;
- pinned runtime lock hash;
- Python runtime version;
- full case-by-case decisions;
- result arithmetic;
- expected decisions;
- critical-family presence and BLOCK requirements;
- saved result identity.

A holdout version is immutable once sealed. Historical/burned results are retained in the source repository for audit transparency but are not packaged as current wheel runtime evidence.

## V11 qualification

V11 is author-curated and not independent external validation.

Result:

- total: **93**;
- unsafe/boundary: **56**;
- unsafe PASS: **0**;
- unsafe BLOCK: **44**;
- unsafe REVIEW: **5**;
- unsafe SOURCE_REVIEW: **7**;
- clean: **37**;
- clean PASS: **37/37**;
- clean REVIEW/BLOCK/SOURCE_REVIEW: **0**;
- expected decisions: **93/93**.

## Additional adversarial development evidence

These are regression/development checks, not independent validation:

- first generated in-profile sweep: **112/112 unsafe BLOCK**, **46/46 clean PASS**;
- later generated unsafe sweep: **49 unsafe transformations, 0 PASS**, plus **11/11 clean equivalents PASS**;
- larger metamorphic comparison sweep: **1,648 expectations, 0 mismatches** across supported aliases, clocks, site changes, force weakening and contact/touch paraphrases;
- context-alignment edge matrix: same waterbody + supported relational suffix MATCH; Stream B/Stream AB collisions MISMATCH;
- malformed API sweep: controlled 4xx responses with no uncontrolled 5xx in tested malformed shapes.

## Packaging/deployment defects found and fixed

### Missing/stale wheel assets

Earlier wheels either missed runtime assets or retained stale resource copies from `build/`.

Fixes:

- package resources are explicitly synchronized;
- `make wheel` deletes `build/`, `dist/` and stale egg-info before building;
- wheel package discovery excludes the repository's release/helper scripts;
- final wheel contains V11 UI/demo/evidence resources and no stale packaged V6/V8/V9 holdout resources;
- installed-wheel runtime was tested outside the source tree.

### Build isolation/network dependency

Default PEP 517 isolation attempted network access for build dependencies in the restricted audit environment. The documented reproducible release path therefore uses the already-pinned local build toolchain:

`python -m pip wheel . --no-deps --no-build-isolation -w dist`

### CI/Docker dependency behavior

CI installs exact dependency locks, then installs the project with `--no-deps --no-build-isolation`.

Docker installs the runtime lock, copies source/runtime evidence, defaults to `AQUASIGNAL_ENV=production`, and therefore refuses to start without a persistent authority secret. Docker execution itself could not be run because Docker is unavailable in the audit environment.

## Security hardening

- CSP with self-only scripts/styles/connect plus anti-framing;
- `X-Content-Type-Options: nosniff`;
- `Referrer-Policy: no-referrer`;
- camera/microphone/geolocation denied through Permissions-Policy;
- early oversized-request responses receive the same security headers;
- dynamic UI values are escaped before HTML insertion;
- long-text similarity visualization is bounded to prevent browser quadratic work;
- optional AI rewrite is disabled by default and requires a separate deployment token when enabled.

## Remaining known limitations

These are deliberately disclosed rather than hidden:

1. **Bounded English V1.** Unsupported natural-language constructions fail closed; AquaSignal is not a general language theorem prover.
2. **Author-curated qualification.** V11 is frozen and useful for anti-tuning, but not independently curated external validation.
3. **Upstream authenticity.** A context token proves the running server imported and bound those bytes; it does not independently prove an uploaded CSV truly originated from OneAquaHealth.
4. **HMAC receipts.** Receipts are verifiable by a deployment sharing the secret, not public-key third-party attestations.
5. **Revision binding, not a supersession registry.** A token is bound to a revision; the standalone prototype does not maintain authoritative global "latest revision" state that revokes all earlier correctly bound revisions.
6. **Optional AI route.** Keep it disabled publicly unless separate authentication, rate/cost controls and monitoring are intentional.
7. **Chunked/edge request enforcement.** Application fields are bounded and Content-Length is rejected early, but a production reverse proxy should also enforce request/body/time limits before the Python app.
8. **No risk inference.** AquaSignal does not determine that a waterbody is unsafe; upstream expert/OAH systems remain responsible for environmental interpretation.
9. **No certification claim.** No production public-health safety certification, FHIR certification, or full OAH IG conformance is claimed.
10. **Docker runtime unverified here.** Configuration is present and hardened, but a real Docker launch still needs to be executed on a host with Docker before claiming it.

## Final engineering recommendation

Freeze the semantic/evaluator V11 dependency set. Do not add features before submission. The remaining high-value work is publication/deployment/video polish, plus an independent external review corpus if the schedule permits without altering the release semantics.
