# AquaSignal v0.4.0 — fourth reliability campaign

## Executive result

AquaSignal v0.4.0 completed a fourth reliability campaign focused on areas not deeply exercised by earlier semantic red teams: strict API data contracts, duplicate JSON keys and alternate encodings, actual request-body limits, context metadata aliasing, FHIR recognized-field validation, algorithmic-complexity bounds, multi-directive rebinding, runtime-version consistency, and Unicode identifier identity.

Final verified state:

- inherited SignalLock regression suite: **611 / 611 passing**;
- AquaSignal-specific automated tests: **263 / 263 passing**;
- combined automated suite: **874 / 874 passing**;
- Aqua DEV: **14 / 14 unsafe BLOCK, 0 unsafe PASS, 10 / 10 clean PASS**;
- frozen author-curated V15: **112 / 112 expected decisions**;
- V15 unsafe/boundary: **69 total — 58 BLOCK, 5 REVIEW, 6 SOURCE_REVIEW, 0 PASS**;
- V15 clean: **43 / 43 PASS**;
- V15 release evidence: **VERIFIED / QUALIFIED**.

These results are bounded prototype evidence, not safety certification or independent external validation.

## 1. API contract ambiguity removed

Earlier request models could accept values through Pydantic coercion, including numeric strings/floats for integer revision fields and string/integer values for booleans. The API now uses strict request typing, so malformed integration payloads fail explicitly instead of being silently reinterpreted.

JSON duplicate keys are rejected before application parsing. The preflight is designed around the behavior FastAPI/Python actually accepts rather than only declared `Content-Type`; regressions cover:

- ordinary JSON;
- missing `Content-Type`;
- UTF-8 BOM;
- UTF-16 and UTF-32 auto-detected JSON;
- nested duplicate object keys.

Request-size enforcement now measures streamed body bytes instead of trusting `Content-Length` alone.

## 2. Context/provenance adapters hardened

Resilience-compatible CSV handling now treats metadata aliases deterministically and based on populated data rather than header presence alone. Fixes include:

- blank preferred `site` can fall back to populated `location`;
- site aliases are merged row-by-row only when consistent;
- conflicting site aliases reject as ambiguous provenance;
- alternate metadata aliases no longer leak into the indicator list;
- date/time aliases fall back to populated values;
- invalid declared ISO date/time values reject.

Recognized FHIR fields such as `status` now have strict types and bounds rather than being silently ignored/truncated when malformed.

## 3. Algorithmic-complexity boundary

A maximum-length advisory can expand into hundreds of distinct directives even though extraction itself remains fast. A deliberately nonmatching ~210×210 action comparison took roughly 1.2 seconds in the audit environment.

Rather than rewriting the inherited deterministic comparator immediately, AquaSignal bounds the public V1 profile to **32 parsed directives** per source/candidate. Over-complex sources go to SOURCE_REVIEW and over-complex candidates go to REVIEW before quadratic comparison. This preserves deterministic correctness while bounding public-path work.

Environment-configured request/advisory limits are validated at startup and reject nonsensical or dangerously large values.

## 4. Multi-directive scope rebinding

A separate composition sweep tested messages where the global bag of actions, sites and times remains unchanged but the bindings are swapped between directives. Examples included action/site and audience/site reassignment. The system never returned PASS; represented critical changes BLOCK and ambiguous rebinding fails closed to REVIEW.

## 5. Python/runtime contract aligned with evidence

The project previously described Python 3.12+ while frozen release evidence/readiness was qualified on Python **3.13.5**. Because Python 3.12 was not available for a complete qualification run, v0.4.0 narrows package metadata and documentation to the exact release-qualified runtime instead of claiming unverified compatibility.

## 6. Unicode identifier identity — P0 finding

The deepest new semantic issue was operational identifier normalization.

NFKC compatibility normalization caused distinct identifiers to collapse:

- `Site ①` → `Site 1`;
- `Site Ａ` → `Site A`;
- `River Ⅳ` → `River IV`;
- `Site ﬁ` → `Site fi`.

An initial repair switched to NFC + Unicode lowercasing. A broader property-style sweep then found another false PASS:

- `Site ϴ` → `Site Θ`.

The reason is Unicode lowercase mapping itself: the Greek capital theta symbol maps into the ordinary theta letter.

### Final rule

Operational identifiers now use:

1. a small explicit allowlist of typography normalization (smart apostrophes, dash variants and nonbreaking spaces);
2. NFC canonical normalization;
3. case normalization only for characters that do **not** have a distinct NFKC compatibility form;
4. no NFKC compatibility folding of identifier identity.

This retains ordinary case-insensitivity and canonical-accent equivalence while preserving compatibility-distinct characters.

A full property sweep across **2,690 compatibility-distinct Unicode word characters** found **0 remaining identifier-key collisions**. Clean controls for smart apostrophes, dash variants, decomposed/precomposed accents and ordinary Unicode case continued to pass.

Context-site deduplication/alignment uses the same identifier identity rule so the verifier and provenance layer cannot disagree.

## 7. Frozen-evidence discipline

V13 was current at the start of this campaign. The semantic identifier change correctly invalidated it.

V14 was then authored with fresh transformed cases, sealed before semantic execution and passed its frozen corpus. A broader post-V14 Unicode property sweep nevertheless exposed the `ϴ`/`Θ` collision. V14 was therefore treated as burned; it was not refreshed or silently resealed.

After the generic fix stabilized, V15 was authored with fresh sites/times and a dedicated critical `identifier_compatibility_change` family. V15 was schema-validated but not semantically executed before sealing.

### V15 identity

- holdout: `aqua-holdout-v15`
- cases: **112**
- unsafe/boundary: **69**
- clean: **43**
- dataset SHA-256: `2a5620f0f7df9f494de53797486dcbfc961d0d7c50f994417a91d55d6b096c44`
- semantic fingerprint: `34781d3c1de2272fc2e42d8c6c2d855d99e8d8ef1610b0b63de41995a307f024`
- evaluator fingerprint: `593bb3fb46f7651e80a87581fca7a0032c42181815f7603a72534e83bdc82665`
- runtime lock SHA-256: `3ee3bc2a8ebc76d265bcdf4d9997b0f60630d0e678faa5b8820d6538f1f00fc3`
- Python: `3.13.5`

V15 passed on first execution:

- unsafe PASS: **0 / 69**;
- unsafe BLOCK: **58 / 69**;
- unsafe REVIEW: **5 / 69**;
- SOURCE_REVIEW: **6 / 69**;
- clean PASS: **43 / 43**;
- expected decisions: **112 / 112**;
- critical identifier-compatibility family: **6 / 6 BLOCK**.

## 8. Installed-artifact verification

The final wheel was built with stale build directories removed and V15 package resources synchronized. Wheel inspection confirmed that the packaged frozen-evidence resources contain **V15 only**.

The wheel was installed outside the source repository. From the installed artifact:

- `/` returned HTTP 200;
- `/api/aqua/health` returned HTTP 200;
- `/api/aqua/demo-context` returned HTTP 200;
- `/api/aqua/release-evidence` returned HTTP 200 and VERIFIED/QUALIFIED V15.

## 9. Production/restart verification

A real production-mode Uvicorn process using the installed wheel and a persistent 32+ byte secret successfully:

- reported READY with V15 evidence;
- minted context/source authority;
- returned BLOCK for AFTER→BEFORE;
- generated and verified an HMAC integrity receipt;
- returned controlled 503 for the optional AI rewrite endpoint when it was disabled.

A second process using the same secret accepted tokens/receipts minted before restart. A third process using a different secret rejected the old authority token and marked the old receipt invalid.

## 10. Reliability conclusion

The fourth campaign found meaningful failures after earlier release gates were already green. In particular, the Unicode identity bug demonstrates why a frozen holdout is evidence about its cases—not proof that the language boundary is complete.

The final release keeps the core architecture narrow:

- deterministic PASS/BLOCK authority;
- unsupported meaning fails closed;
- explicit complexity limits;
- strict API contracts;
- conservative operational-identifier identity;
- context/source/candidate cryptographic binding;
- human publication authority.

No new dashboard, prediction model, agent framework or broad language claim was added during hardening.

## Remaining limits

- English Freshwater Protective Communication Profile v1 is intentionally bounded;
- V15 is author-curated, not independent external validation;
- upstream data authenticity is not independently attested by AquaSignal;
- HMAC receipts are server-verifiable, not public-key/nonrepudiation artifacts;
- Docker configuration exists but Docker execution is not verified in this audit environment;
- broader multilingual/ecological/operational validation remains future work.
