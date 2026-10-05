# SignalLock v0.10 — Fourth-Order Hardening Report

## Scope

This pass attacked the v0.9 semantic and qualification-evidence boundary after the v0.9 evidence-boundary gate was already green. The target was not to increase benchmark scores; it was to find ways a dangerous multilingual meaning change or edited qualification artifact could still be accepted as trustworthy.

## Failures found and repaired

### F-1001 — Native Hindi/Telugu negation could survive as a positive action

The native semantic guard recognized several action words but did not robustly bind explicit negation to action polarity. Minimal commands such as Hindi `निकासी न करें।` and Telugu `బయటకు వెళ్లవద్దు.` could be represented as positive `MUST` actions without an independent semantic contradiction.

**Repair:** explicit native negation is detected before action classification and cross-checked against action negation, modality, and required/prohibited list placement. A negative phrase represented as a positive required action is now fail-closed before provider-derived evidence is accepted.

### F-1002 — Provider model identity could be invented locally

A qualification receipt could substitute the locally configured model when the provider response omitted its model identity.

**Repair:** the qualification evidence path requires the provider response itself to report a non-empty response ID and model. Missing provider model identity is rejected; there is no local identity fallback for certification evidence.

### F-1003 — Provider configuration binding was self-referential

Runtime verification could reconstruct the expected provider-config fingerprint from configuration already supplied by the manifest rather than independently from code-owned runtime behavior.

**Repair:** the OpenAI qualification configuration is now code-owned. Strict sealing and replay compare the manifest binding against that independently reconstructed runtime configuration.

### F-1004 — Checkpoint evidence could be relabeled as fresh

A resumed case was primarily identified by a mutable `recovered_from_checkpoint` flag.

**Repair:** checkpoint format 4.0 stores the originating and executing run IDs. Every fresh case must bind both to the current run; recovered cases preserve their prior origin. Clearing the recovery flag alone makes replay fail.

### F-1005 — Candidate contract was not reconstructibly bound to provider output

A saved candidate contract hash and a provider-output hash could each be internally valid while referring to different semantic objects.

**Repair:** successful provider evidence retains the exact structured output text plus its SHA-256. Replay reparses that exact output through the frozen extraction/semantic-guard path and requires the reconstructed candidate contract hash to equal the saved contract hash before verification is replayed.

### F-1006 — Blind-review mapping task reassociation

The private review mapping could be edited after reviewers completed opaque sheets, reassigning review IDs to different authored tasks.

**Repair:** mapping format 3.0 binds every review entry to both the authored content hash and a task/content binding hash, plus a mapping-wide integrity hash. Reassociation fails even if an attacker recomputes the outer mapping hash.

### F-1007 — Source-language/diversity gaming

Strict V7 quality did not sufficiently reject non-English authority labels or numeric/punctuation variants masquerading as distinct source diversity.

**Repair:** authoritative V7 source language must be `en`; normalized source-family diversity collapses numeric/punctuation clones and is enforced overall and per language.

### F-1008 — Unicode format-character reviewer aliases

Zero-width format characters could make visually identical reviewer/author IDs compare as different strings.

**Repair:** role identities are NFKC-normalized and Unicode format characters are removed before independence checks.

### F-1009 — Browser live-session cookie exposed the master token

The browser session previously reused the master live-provider token in a non-Secure cookie.

**Repair:** authenticated session creation now mints an independent short-lived random capability stored server-side. The browser cookie is `HttpOnly`, `Secure`, `SameSite=strict`, and time-limited; it never contains the master token.

### F-1010 — API/package version drift

The FastAPI version could diverge from the packaged project version.

**Repair:** API version is read from the canonical `pyproject.toml` project version.

### F-1011 — Private blinded-review map was not ignored under its real filename

The scripts write `data/multilingual/v7_blind_review_map.json`, while `.gitignore` only listed an obsolete mapping filename.

**Repair:** the actual blind map, authority-draft output, exploratory review draft, authored/reviewer sheets, and reviewed holdout are ignored by default. A regression test pins these private-workflow exclusions.

## Regression evidence

- Automated tests: **184/184 PASS**.
- New fourth-order hardening regressions: **14/14 PASS**.
- DEV benchmark: **108 cases**.
  - unsafe: **0/76 PASS; 76/76 BLOCK**.
  - clean: **32/32 PASS; 0/32 BLOCK**.
- Post-repair forensic audit: **PASS**.
- Second-order relational audit: **PASS**.
- Independent v0.10 retest of the original F-1001–F-1010 exploit classes: **all blocked**.
- Unblocked Critical findings from that retest: **0**.
- Unblocked High findings from that retest: **0**.

## Evidence boundary that intentionally remains

Provider response IDs/model fields/raw structured output are strong replay/audit evidence inside this system, but they are not externally signed cryptographic attestations from the provider. Human reviewer IDs/timestamps are process evidence, not cryptographic identity proof. SignalLock also does not yet have a genuine independently authored/reviewed Hindi/Telugu V7 holdout result from this v0.10 runtime.

## Promotion decision

**Promote the qualification/tooling runtime to v0.10. Keep V7 multilingual model-quality qualification and V8/submission locked.** The next legitimate stage is external evidence collection: independent human holdout production followed by a fresh 24/24 provider-backed run under the frozen v0.10 runtime/model and successful replay/V8 unlock.
