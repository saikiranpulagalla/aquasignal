# AquaSignal demo script — target 3:45 to 4:15

## 0:00–0:20 — Hook

“An AI-generated freshwater warning can sound completely fluent while silently changing the action citizens are supposed to take. If `after 6 PM` becomes `before 6 PM`, linguistic quality is not the problem — operational meaning is.”

Show the title:

**AquaSignal — Verified Freshwater Risk Communication**

“AI may rewrite the warning. It may not rewrite the protective action.”

## 0:20–0:45 — OneAquaHealth fit

“OneAquaHealth already provides tools that turn environmental observations into usable intelligence. AquaSignal protects the last mile between that intelligence, a human-authored advisory, and AI-assisted citizen communication.”

Click **Load synthetic OAH context**.

Point out:

- synthetic demo label,
- site,
- indicators,
- dataset SHA-256.

Say explicitly: “AquaSignal does not decide that the water is dangerous. This context is provenance. A human authority owns the advisory.”

## 0:45–1:25 — Hero time inversion

Choose **Time inversion**.

Source:

`Visitors must avoid contact with Stream A after 18:00.`

Candidate:

`Visitors must avoid contact with Stream A before 18:00.`

Point to the naive similarity percentage first.

Click **Verify protective meaning**.

Expected result: **CRITICAL DRIFT**.

Point to:

`TIME: AFTER 18:00 → BEFORE 18:00`

“Most of the words survived. The protective action did not.”

## 1:25–1:55 — One Health audience loss

Choose **Audience loss**.

Source:

`Keep children and pets away from Stream A until 18:00.`

Candidate:

`Keep children away from Stream A until 18:00.`

Verify.

Expected: **CRITICAL DRIFT**.

“This is why audience is a first-class invariant. A small edit removed the animal-health part of the One Health instruction.”

## 1:55–2:20 — Freshwater spatial reversal

Choose **Flow reversal**.

Show:

`downstream of Bridge A` → `upstream of Bridge A`

Expected: **CRITICAL DRIFT**.

“The generic SignalLock engine did not originally know that upstream and downstream are freshwater opposites. AquaSignal adds that deterministic domain policy without rewriting the mature comparator.”

## 2:20–2:40 — Prove it is useful, not just conservative

Choose **Safe 6 PM → 18:00**.

Verify.

Expected: **PRESERVED**.

“A useful integrity checker must recognize supported equivalence instead of sending everything to review.”

## 2:40–3:10 — Trust architecture

Open technical evidence briefly.

Explain only four boundaries:

1. source must pass **Source Readiness**;
2. source + context + revision are server-bound;
3. AI can propose wording but cannot approve itself;
4. deterministic comparison owns the verdict.

Do not explain legacy CAP or multilingual research unless asked.

## 3:10–3:35 — Evaluation evidence

Run/show Aqua DEV metrics:

- 14 unsafe BLOCK,
- 0 unsafe PASS,
- 10 clean PASS.

Then state:

“The combined automated suite currently collects 962 tests — 611 inherited SignalLock regressions and 351 Aqua-specific tests. Final qualified execution is pending on the sealed Python 3.13.5 environment. Our frozen author-curated V17 holdout has 73 cases: 47 unsafe/boundary with 0 PASS, and 26 out of 26 clean cases PASS. Unsafe cases that are fully represented BLOCK; unsupported or ambiguous cases fail closed to REVIEW or SOURCE REVIEW.”

Important credibility line:

“Our first holdout actually failed: it found an unauthorized `fish` → `fish or swim` addition that passed. We kept that failed evidence. Later hardening checkpoints were also burned whenever semantics or evaluation changed. V17 was sealed only after the sixth reliability campaign stabilized and then executed once. These are prototype results, not independent validation or safety certification.”

## 3:35–3:55 — Integrity receipt / scale

Click **Download integrity receipt**.

“AquaSignal is not another water dashboard. The output is a portable verification receipt with hashes, profile version, advisory revision and field-level differences, so the same gateway can sit between existing environmental systems and publication channels.”

## 3:55–4:10 — Close

“AquaSignal preserves the authority of environmental experts while making AI-assisted communication safer to review.”

End on:

**AI may rewrite the warning. It may not rewrite the protective action.**

## Judge Q&A answers

### Does AquaSignal decide if water is safe?

No. Environmental experts/upstream OneAquaHealth systems own risk assessment. AquaSignal verifies communication integrity after an advisory exists.

### Is an LLM checking another LLM?

No. The supported V1 PASS path is deterministic. The AI rewrite endpoint is proposal-only and has no authority in verification.

### What if the source itself is ambiguous?

Source Readiness refuses to freeze unresolved operational meaning. The product shows SOURCE REVIEW rather than pretending the source is machine-verifiable.

### Why OneAquaHealth?

AquaSignal consumes environmental context from the same type of export/integration boundary OneAquaHealth tools expose and adds a missing downstream trust layer before citizen communication.

### Is it FHIR certified?

No. The prototype has a bounded environmental FHIR R4-subset context adapter and records declared profiles; no certification or complete IG conformance is claimed.

### Why keep SignalLock tests?

Because the generic verifier is reused infrastructure. Preserving its 611-test regression boundary lets the hackathon adaptation prove it did not silently break the core.
