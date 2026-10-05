# AquaSignal v0.6.1 — Seventh Reliability Campaign

## Scope

This campaign started from the exact v0.6.0/V17 handoff and intentionally targeted areas not deeply exercised by the first six campaigns: provenance exactness, CSV metadata alias consistency, read-only deployment, timezone/locale determinism, malformed JSON parser limits, log/privacy behavior, HTTP range/cache semantics, and bounded-resource behavior.

No V17-sealed semantic/evaluator dependency was changed. V17 therefore remains the current frozen semantic release evidence.

## Confirmed defects fixed

### Exact advisory provenance

The API previously called `.strip()` inside `_guard_text()`. This meant authority/source hashes and receipt hashes were computed over a trimmed advisory rather than the literal text submitted by the reviewer.

Repair: emptiness is now checked with `value.strip()`, but the exact submitted source/candidate string is retained for extraction, authority binding, SHA-256 receipt fields, and evidence offsets. A token minted for a whitespace-different source no longer verifies a trimmed variant.

### Conflicting date/datetime aliases

Resilience-compatible CSVs can contain multiple metadata aliases such as `date`, `timestamp`, and `datetime`. The importer previously selected one by priority without proving other populated aliases were compatible.

Repair: populated full date/datetime aliases on the same row must be compatible. Date-only plus timestamp is accepted when they represent the same local calendar date; full timestamps with different offsets are accepted when they represent the same instant. Conflicts are rejected.

### Sparse timestamp fallback

A globally preferred timestamp column could be blank on some rows while a lower-priority date column was populated, causing the displayed date range to omit rows.

Repair: date-range metadata is selected row-by-row using the highest-priority populated full date/datetime alias.

### Time-only CSV metadata

A `time`-only metadata column (for example `18:00`) was recognized as metadata but then rejected as an invalid full ISO datetime.

Repair: time-only fields remain metadata but do not create or invent a calendar `date_range`.

### Extreme JSON integer 500

Python's JSON decoder can raise plain `ValueError` when an integer literal exceeds `sys.int_max_str_digits`. The request preflight did not classify that exception, allowing a bounded hostile JSON body to escape as HTTP 500 without normal API cache/security headers.

Repair: parser-limit `ValueError`s now become controlled HTTP 422 responses with `Cache-Control: no-store` and the normal security headers. Duplicate-key and ordinary malformed-JSON handling remain separate.

## New verification angles that passed

- real unprivileged execution from a recursively read-only source tree;
- context-token canonicalization across reordered dictionaries;
- timezone-independence across UTC, Asia/Kolkata, America/New_York, and Pacific/Kiritimati;
- integrity-receipt model/JSON round-trip signature verification;
- invalid-request advisory marker did not appear in sanitized HTTP validation responses or Uvicorn access logs;
- static byte-range responses retained CSP and `no-cache`;
- API 405/validation responses retained `no-store`/security headers;
- 20,000-row CSV parsing remained bounded (~0.1 s in the audit environment);
- 200-entry bounded FHIR coding input remained sub-millisecond in the audit environment;
- near-8,000-character unsupported advisory extraction remained millisecond-scale;
- malformed transport matrix produced no uncontrolled 5xx after repair.

## Changes deliberately rejected

### CR-only list-line expansion

A narrow parser change could make legacy `\r`-only list boundaries behave like LF/CRLF. The input currently fails closed to SOURCE_REVIEW. Implementing the improvement would change `aquasignal/domain/freshwater.py`, which is V17-sealed. Because this is a low-severity usability edge rather than an unsafe PASS, the change was rolled back instead of burning V17.

### Broader Python installation range

Changing `requires-python` from exact `3.13.5` to `>=3.13,<3.14` would make installation easier on later 3.13 patch releases. However those runtimes were not actually qualified. An existing release-invariant test correctly rejected the unproven compatibility claim, so the metadata remains exact `3.13.5`.

### Unverifiable wheel build-tool pin

Pinning `wheel`/`setuptools` in the development lock was explored, but the audit environment exposed `wheel` as importable without distribution metadata, causing the exact lock gate to fail. The proposed pin was rolled back rather than weakening `_verify_lock`. The documented `--no-build-isolation` release path remains.

## Evidence discipline

The campaign demonstrates a key reliability rule: not every behavior improvement is a release improvement. Proposed fixes were retained only when they could be proven without weakening frozen evidence, lock verification, or qualification claims.

V17 remains author-curated frozen evidence, not independent external validation.
