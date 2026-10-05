# AquaSignal screenshot capture guide

Capture screenshots from the AquaSignal UI, not the inherited SignalLock UI.

## 1. Hero / context

- load the synthetic OAH/Resilience context;
- include title/tagline, context provenance, source and candidate panels;
- ensure the `SYNTHETIC DEMO` label and Track 6 wording are visible.

Suggested filename: `docs/images/aquasignal-overview.png`

## 2. Critical time drift

Source: `Visitors must avoid contact with Stream A after 18:00.`

Candidate: `Visitors must avoid contact with Stream A before 18:00.`

Expected: **CRITICAL DRIFT**, with TIME evidence.

Suggested filename: `docs/images/aquasignal-time-drift.png`

## 3. One Health audience loss

Source: `Keep children and pets away from Stream A until 18:00.`

Candidate: `Keep children away from Stream A until 18:00.`

Expected: **CRITICAL DRIFT** with missing `pets` evidence.

Suggested filename: `docs/images/aquasignal-audience-drift.png`

## 4. Safe equivalence

Source: `Visitors must avoid contact with Stream A until 6 PM.`

Candidate: `Visitors must avoid contact with Stream A until 18:00.`

Expected: **PRESERVED**.

Suggested filename: `docs/images/aquasignal-preserved.png`

## Capture checklist

- no browser console/devtools in frame;
- no secret/API key;
- synthetic context visibly labeled;
- human-authority disclaimer visible where possible;
- no old SignalLock emergency-alert page;
- use the release candidate commit/artifact that passed `python scripts/release_gate.py`.
