# AquaSignal reuse disclosure

## Purpose

AquaSignal is a OneAquaHealth-specific product adaptation built on a pre-existing generic integrity architecture. This document makes that boundary explicit so the submission does not imply that earlier SignalLock work was created during the OneAquaHealth hackathon.

## Pre-existing lineage

The following capability lineage predates AquaSignal:

- generic typed `SafetyContract` schema,
- deterministic SignalLock verification engine,
- generic emergency-alert extraction/normalization logic,
- CAP tooling,
- SignalLock provider/evaluation infrastructure,
- inherited emergency-domain tests and historical qualification material.

These remain under `signallock/`, `apps/api/`, `web/`, inherited `tests/`, and historical documentation. They are preserved chiefly as a regression boundary for the reused integrity engine.

Original public SignalLock repository supplied by the participant:

`https://github.com/saikiranpulagalla/signallock-emergency-alert-integrity-checker`

## New AquaSignal / OneAquaHealth work

The Aqua-specific layer is separated into new paths and capabilities:

- `aquasignal/domain/context.py` — Resilience Map CSV and bounded environmental FHIR provenance adapters;
- `aquasignal/domain/freshwater.py` — deterministic Freshwater Protective Communication Profile v1;
- `aquasignal/integrity/authority.py` — source + environmental-context + revision + profile binding;
- `aquasignal/integrity/verifier.py` — freshwater-specific semantic policy, including flow direction, site identifiers and prohibition-force invariants;
- `aquasignal/integrity/receipt.py` — machine-readable integrity receipts;
- `aquasignal/providers/rewrite.py` — optional proposal-only freshwater rewrite path with no verification authority;
- `apps/aqua_api/` — AquaSignal API/product surface;
- `web_aqua/` — AquaSignal judge-facing UI;
- `data/aqua/` — Aqua demo context and evaluation corpora;
- `tests/aqua/` — Aqua-specific semantic, context, API, security and UI tests;
- `scripts/*aqua*` — Aqua DEV/holdout/evidence tooling;
- AquaSignal README, architecture, validation, submission and demo documentation.

## No misleading test-count claim

The inherited **611** tests validate the SignalLock lineage. They are not described as freshwater tests.

AquaSignal adds **335** Aqua-specific automated tests. The combined repository currently contains **946** passing tests. The README keeps inherited SignalLock evidence and new freshwater evidence separate.

## Evaluation disclosure

The Aqua DEV set is developer-visible and used during implementation.

Aqua holdout V1 was author-curated, sealed, and failed because one unauthorized coordinated action received PASS. That result is retained as burned evidence. Later red-team passes deliberately burned additional checkpoints when defects or post-seal semantic/evaluator changes were found. The current author-curated V17 holdout contains 73 cases, was sealed before execution, and qualified with 0 unsafe PASS and 26/26 clean PASS. None of these sets is described as independent external validation.

## Eligibility

The official hackathon rules state that projects must be original and developed during the hackathon period. AquaSignal therefore exposes the pre-existing/new boundary rather than obscuring it. The participant should retain any organizer clarification regarding reuse of participant-authored open-source components as part of the submission record.
