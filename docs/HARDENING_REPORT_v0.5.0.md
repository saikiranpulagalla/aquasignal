# AquaSignal v0.5.0 — fifth reliability campaign

## Executive result

AquaSignal v0.5.0 completed a fifth reliability campaign focused on failure classes that were not deeply exercised by the earlier semantic red teams: real-world visual formatting, environmental-FHIR privacy/scope, raw provenance preservation, extreme timestamp handling, browser request races, malformed proxy responses, cross-protocol token replay, FHIR status-code validation, deeply nested JSON request exhaustion, and post-fix clean/unsafe metamorphic behavior.

Final verified state:

- inherited SignalLock regression boundary: **611 / 611 passing**;
- AquaSignal-specific automated tests: **317 / 317 passing**;
- combined automated suite: **928 / 928 passing**;
- Aqua DEV: **14 / 14 unsafe BLOCK, 0 unsafe PASS, 10 / 10 clean PASS**;
- frozen author-curated V16: **76 / 76 expected decisions**;
- V16 unsafe/boundary: **46 total — 40 BLOCK, 4 REVIEW, 2 SOURCE_REVIEW, 0 PASS**;
- V16 clean: **30 / 30 PASS**;
- V16 release evidence: **VERIFIED / QUALIFIED**.

This remains prototype evidence, not safety certification or independent external validation.

## 1. Visual line wrapping changed verdicts

### Failure

A supported directive such as:

```text
Do not swim in Stream A
until 18:00.
```

could fail source readiness or compare differently from the single-line equivalent. This is realistic when advisories are copied from PDFs, email, SMS editors, or narrow browser windows.

### Repair

The parser now creates a same-width scan view in which CR/LF are treated as presentation whitespace while evidence offsets still point into the original source text. Sentence punctuation continues to define semantic boundaries.

Regression coverage includes LF, CRLF, line breaks across multiple supported token boundaries, exact evidence quotes/offsets, and complete API authority→verify round-trips.

A metamorphic sweep across 41 word boundaries and multiple whitespace forms produced no clean-equivalence failures.

## 2. Common list formatting was unnecessarily rejected

### Failure

Line-leading list markers such as:

```text
- Do not swim ...
• Do not fish ...
1) Do not wade ...
```

were interpreted as unsupported operational text.

### Repair

Only common **line-leading** bullet/ordered-list decoration is blanked in the same-width scan view. Inline hyphens, numbers, punctuation, identifiers, and semantic text remain untouched. Evidence offsets continue to index exact original directive text.

This is intentionally narrow; unsupported list content still fails closed.

## 3. Environmental FHIR accepted clinical references

### Failure

The environmental adapter accepted an `Observation` whose subject referenced `Patient`, `Encounter`, `Practitioner`, or other clinical resources, and could ignore nested clinical references/resources.

That contradicted AquaSignal's declared environmental-only scope.

### Repair

The adapter now:

- accepts only environmental `Observation` or `Location` root resources;
- requires an `Observation.subject.reference`, when present, to target `Location`;
- iteratively rejects clinical resource types and clinical references anywhere in the supplied resource;
- retains positive controls for relative and absolute `Location/...` references;
- returns controlled 422 responses rather than 500-class errors.

The adapter remains a bounded **FHIR R4 subset**, not a full validator or certification claim. The current OneAquaHealth CI implementation guide is based on FHIR 4.0.1.

## 4. Recognized FHIR status fields were too permissive

### Failure

If `status` was present, arbitrary strings such as `banana` or uppercase noncanonical values could be stored as provenance metadata.

### Repair

For the recognized R4 fields AquaSignal now validates exact code-system values:

- Observation: `registered`, `preliminary`, `final`, `amended`, `corrected`, `cancelled`, `entered-in-error`, `unknown`;
- Location: `active`, `suspended`, `inactive`.

This validates a known field only; it does not convert the adapter into a complete FHIR-conformance validator.

## 5. Raw FHIR provenance could be canonicalized in the browser

### Failure

The original browser path performed `JSON.parse()` before sending FHIR to the server. That caused two problems:

1. duplicate JSON keys could be silently collapsed before server validation;
2. the recorded SHA-256 represented a browser-reserialized object rather than the exact pasted JSON text.

### Repair

A raw-FHIR endpoint now receives exact pasted UTF-8 JSON text, rejects duplicate keys server-side, validates the bounded environmental subset, and hashes the exact received bytes. The structured endpoint remains for compatibility.

## 6. CSV file decoding could silently alter bytes

### Failure

`File.text()` may replace malformed UTF-8. Default BOM behavior could also make browser-imported content hash differently from the uploaded valid UTF-8 byte sequence.

### Repair

The browser path now uses fatal UTF-8 decoding and explicitly preserves a valid UTF-8 BOM. Invalid UTF-8 is rejected before import rather than silently replaced.

## 7. Context-import requests could race in the browser

### Failure

If a user started two asynchronous context imports, an older slower response could overwrite the newer selection.

### Repair

Context loading is now generation-bound (`last request wins`). Both successful and failed stale responses are ignored if a newer import exists. Authority state is invalidated whenever the accepted context changes.

## 8. Non-JSON reverse-proxy errors produced opaque browser failures

### Failure

The browser assumed every response body was JSON. An upstream HTML/text 413/502 could therefore become a JSON parsing error rather than the actual HTTP failure.

### Repair

The client reads response text first, parses JSON when possible, and otherwise reports a bounded HTTP status/body message.

## 9. Extreme ISO offsets could escape as `OverflowError`

### Failure

Syntactically valid extreme datetimes near years 0001/9999 with timezone offsets could overflow during UTC normalization and become uncontrolled API 500s.

### Repair

Timezone normalization traps overflow/value errors and turns them into deterministic provenance-validation failures. Date ordering now compares timezone-aware UTC datetimes directly rather than relying on platform-sensitive timestamps.

Ordinary ISO dates and offset datetimes remain accepted.

## 10. Deep JSON could exhaust decoder recursion before FHIR guards

### Failure

A JSON body well under the byte limit but approximately 10,000 levels deep could trigger Python JSON decoder recursion inside the duplicate-key middleware, producing HTTP 500 before the FHIR depth validator ran.

### Repair

Decoder `RecursionError` is now converted at the earliest request boundary to a controlled 422 response with normal API `no-store` and browser security headers. Moderate excessive nesting still reaches the FHIR-specific maximum-depth guard and is rejected there.

## 11. Token protocol separation received explicit negative coverage

Context and authority tokens already contain distinct signed `kind` values. The fifth campaign added negative tests proving a valid context token cannot be replayed as an authority token and vice versa.

No protocol-logic change was required.

## 12. Candidate-side unknown-action sweep

A separate adversarial vocabulary sweep appended unsupported operational instructions to an otherwise preserved candidate, including examples such as:

- `Wear boots.`
- `Use gloves.`
- `Do not kayak.`
- `Keep livestock away.`
- `Call emergency services.`
- `The water is safe to drink.`

Every tested unsupported addition prevented automatic PASS and produced REVIEW. Inline punctuation variants (`;`, comma, em dash, colon, slash, conjunctions, newline) also remained fail-closed.

## 13. Whitespace and confusable metamorphic checks

Supported directives were mutated across ordinary spaces, repeated spaces, tab, LF, CRLF, NBSP, narrow NBSP, and thin-space boundaries. The tested clean variants preserved PASS.

Confusable identifier/keyword substitutions did not silently normalize into an unsafe PASS. Unsupported confusable keywords produced REVIEW; a different confusable site identifier remained a different site and BLOCKed.

## 14. V15 was correctly burned

The line-layout parser change modified a V15-sealed semantic dependency. V15 therefore became stale and was not refreshed in place.

After the fifth campaign stabilized, a new fresh V16 corpus was authored. The exact V16 cases were not semantically executed before sealing.

## V16 frozen identity

- holdout: `aqua-holdout-v16`
- cases: **76**
- unsafe/boundary: **46**
- clean: **30**
- dataset SHA-256: `b2950a205d37a562f68c46a320294ffc02197f6be96a48fff52395b5133f480a`
- semantic fingerprint: `6f55da83746631c20255ec6470ab75c2b6d41246093c2200efb912051712c1e7`
- evaluator fingerprint: `ac40f5c795a1e4e836a13a8f6d3ea8277e033c972cc69598cbaa17d21726c271`
- requirements lock SHA-256: `3ee3bc2a8ebc76d265bcdf4d9997b0f60630d0e678faa5b8820d6538f1f00fc3`
- sealed Python: **3.13.5**

V16 passed on first execution:

- unsafe PASS: **0 / 46**;
- unsafe BLOCK: **40 / 46**;
- unsafe REVIEW: **4 / 46**;
- unsafe SOURCE_REVIEW: **2 / 46**;
- clean PASS: **30 / 30**;
- clean REVIEW/BLOCK: **0 / 30**;
- expected decisions: **76 / 76**.

New V16 families include visual-layout equivalence, unsupported candidate additions expected to REVIEW, unsupported authoritative sources expected to SOURCE_REVIEW, directive reorder equivalence, duration-unit equivalence, and noon/midnight equivalence, in addition to every declared critical BLOCK family.

## 15. Production/process/package verification

After V16 was sealed, no V16-sealed semantic/evaluator file was modified.

A real production-mode Uvicorn process with a persistent 32+ byte secret passed:

- `/api/aqua/health`;
- `/api/aqua/ready` reporting v0.5.0 + V16;
- demo-context import/token minting;
- Source Readiness;
- AFTER→BEFORE `BLOCK`;
- signed receipt verification;
- `/api/aqua/release-evidence` VERIFIED;
- homepage/security headers;
- 10,000-level nested-JSON rejection as controlled 422/no-store.

A clean v0.5.0 wheel was built and installed outside the source repository. From the installed wheel alone, `/`, health, demo context, release evidence, and readiness all returned 200 with V16.

## Current boundaries intentionally retained

- The supported English profile is deliberately narrow; unrelated boilerplate in the authoritative source may produce SOURCE_REVIEW rather than being guessed harmless.
- Tokens bind revision but the standalone prototype does not maintain a global supersession/revocation registry.
- Tokens do not currently expire; production governance would need an explicit lifecycle policy rather than an arbitrary hackathon TTL.
- Environmental FHIR support is a bounded R4 subset, not full FHIR/OAH conformance certification.
- Server-bound context provenance proves which bytes AquaSignal imported, not independent authenticity of the upstream provider.
- V16 is author-curated, not independent external validation.
- The deterministic V1 path is English-only and human approval remains mandatory.

## Engineering decision

No further semantic feature expansion is recommended before submission. The fifth campaign found and closed meaningful reliability gaps without weakening fail-closed behavior, and V16 is now the semantic freeze. Further semantic changes require a new holdout version rather than modifying V16.
