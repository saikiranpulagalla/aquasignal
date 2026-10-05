# AquaSignal — Devpost submission draft

## Project title

**AquaSignal — Verified Freshwater Risk Communication**

## Track

**Track 6 — Resilience Informatics**

## Tagline

**AI may rewrite the warning. It may not rewrite the protective action.**

## One-line description

AquaSignal is a human-review integrity gateway that verifies whether AI-assisted freshwater advisories preserve critical action, place, time, audience and constraints before citizen publication.

## Problem

Environmental early-warning systems are only useful if their protective meaning survives the last communication step. An AI rewrite can be fluent and highly similar to the authoritative advisory while reversing `after` to `before`, changing `downstream` to `upstream`, dropping `pets` from an audience, weakening `must` to `should`, or inventing new health advice.

Generic text similarity is not enough for those failures.

## Solution

AquaSignal binds OneAquaHealth-style environmental context to a human-authored freshwater advisory, checks whether the source can be represented under a declared deterministic profile, freezes that source into a server-bound authority envelope, and then independently verifies any citizen-facing rewrite.

The supported V1 verifier compares:

- ACTION,
- PLACE,
- TIME,
- AUDIENCE,
- CONSTRAINT.

It returns **PRESERVED**, **REVIEW**, or **CRITICAL DRIFT** and leaves final publication authority with a human.

## OneAquaHealth integration

The primary demo path accepts a Resilience Map-style CSV export and preserves its site/date/indicator provenance without pretending to infer environmental risk from values. A secondary bounded environmental FHIR R4-subset JSON adapter supports `Observation`/`Location` context while explicitly avoiding certification or patient-data claims.

AquaSignal is designed to sit downstream of environmental monitoring/analysis and upstream of notification/publication channels.

## Primary user

Environmental/public-health communication officer or municipal environmental officer responsible for converting environmental-risk intelligence into citizen-facing guidance.

## One Health impact

AquaSignal protects the integrity of advice that can affect:

- people using urban waterways,
- children and other named human audiences,
- pets/animals,
- behavior around freshwater ecosystems.

It complements ecological monitoring rather than replacing it.

## Innovation

Most hackathon solutions focus on detection, scoring, maps, prediction or dashboards. AquaSignal focuses on a different failure boundary: **semantic drift introduced while authoritative environmental guidance is transformed for communication**.

Key design rule:

> The model that writes the message never gets to certify its own output.

AI can propose wording. Automatic PASS uses only the deterministic freshwater profile and deterministic verification core. Unsupported meaning fails closed to REVIEW.

## Technical implementation

- Python / FastAPI / Pydantic
- deterministic Freshwater Protective Communication Profile v1
- context-bound HMAC authority envelope
- freshwater semantic policy for flow direction, site identifiers and prohibition force
- inherited SignalLock deterministic verification engine
- machine-readable integrity receipts
- Resilience CSV + environmental FHIR R4-subset context adapters
- accessible plain HTML/CSS/JavaScript UI
- optional OpenAI proposal-only rewrite endpoint
- pytest + sealed evaluation evidence tooling

## Validation

Current bounded prototype evidence:

- **611/611** inherited SignalLock regression tests pass;
- **351** Aqua-specific tests are collected; final qualified execution is pending;
- **962** automated tests are collected; final qualified execution is pending;
- Aqua DEV: **14 unsafe BLOCK / 0 unsafe PASS / 10 clean PASS**;
- frozen author-curated Aqua holdout V17: **73 cases — 47 unsafe/boundary with 0 PASS (40 BLOCK / 4 REVIEW / 3 SOURCE_REVIEW) and 26/26 clean PASS**.

The first frozen Aqua holdout found one unsafe PASS in coordinated-action parsing. That failed V1 result is retained. Subsequent hardening checkpoints were treated as burned whenever a defect or post-seal change invalidated them. V17 is the current sealed result: it was not executed before sealing and is not claimed as independent external validation.

## Demo story

1. Load clearly labeled synthetic OneAquaHealth-style/Resilience context.
2. Source: `Visitors must avoid contact with Stream A after 18:00.`
3. Rewrite: `... before 18:00.`
4. Despite ~95% textual similarity, AquaSignal flags **CRITICAL DRIFT: AFTER → BEFORE**.
5. Show `children and pets` → `children` audience loss.
6. Show `downstream` → `upstream` location reversal.
7. Show safe `6 PM` → `18:00` equivalence returning **PRESERVED**.
8. Download the integrity receipt and show source/context/candidate hashes.

## Why it is practical

AquaSignal is an integration gateway, not another environmental data platform. Existing monitoring/resilience systems can remain responsible for environmental evidence and risk interpretation. AquaSignal adds a narrow verification step where human-approved guidance is transformed for a different channel or audience.

## Scalability path

- REST API boundary,
- context adapters rather than hard-coded upstream system,
- deterministic profile version in every receipt,
- revision-bound authority,
- portable machine-readable result,
- future adapters for notification systems, citizen-science workflows and broader standards profiles.

## Limitations

AquaSignal is a research/hackathon prototype, not public-health authority, environmental certification, FHIR certification, or guarantee of language coverage. English V1 is intentionally bounded. Environmental context is not used to infer health risk. PASS remains subject to human approval.

## Reuse disclosure

The generic SignalLock integrity engine predates this submission. AquaSignal explicitly separates and documents the new OneAquaHealth-specific product layer, freshwater semantics, context binding/adapters, Aqua evaluation, UI/API and release evidence. See `docs/REUSE_DISCLOSURE.md`.
