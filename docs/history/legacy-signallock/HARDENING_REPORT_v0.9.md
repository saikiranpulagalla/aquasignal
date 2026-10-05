# SignalLock v0.9 — V7 Evidence-Boundary Hardening Report

## Scope

This pass attacked the qualification/evidence boundary after v0.8, not the core semantic verifier. The goal was to determine whether a locally modified manifest/result/replay receipt or weak provider receipt could make V8 accept evidence that did not actually correspond to the frozen strict V7 evaluation.

## Critical findings fixed

### F-901 — Manifest quality was trusted during replay

v0.8 recomputed case decisions and metrics, but supplied the metric quality/diversity block from `manifest["quality"]`. Because the manifest file itself is not the sealed JSONL payload, coordinated local edits could change claimed reviewer/diversity/fault coverage without changing the sealed holdout SHA-256.

**Fix:** production replay now runs the strict V7 quality validator over the exact sealed rows and requires the recomputed quality object to equal the manifest quality block.

### F-902 — Production replay did not re-check strict runtime binding

v0.8 replay checked the result/runtime tree but did not independently require the manifest to be a strict V7 manifest or re-run its provider/model/prompt/schema fingerprint verification.

**Fix:** production replay requires `strict_v7=true`, re-verifies the frozen provider/model/config/prompt/schema fingerprint, and re-checks code/release identity.

### F-903 — Provider receipt model was not enforced

The receipt stored `response_model`, but replay did not require it to equal the sealed model.

**Fix:** every successful live case must report the exact frozen model in its provider receipt.

### F-904 — Provider response receipt reuse was not detected

A repeated response ID across cases was not rejected.

**Fix:** successful V7 response IDs must be unique across the run. Reuse fails replay.

### F-905 — V8 receipt binding omitted manifest/run/runtime fields

V8 compared the persisted replay receipt to the result/holdout but did not also bind the exact manifest file, run ID, provider, model, replayed gate, and runtime identity.

**Fix:** V8 now cross-checks all of those fields against a fresh replay.

## Regression evidence

- Automated tests: **170/170 PASS**
- DEV benchmark: **108 cases**
- Unsafe PASS: **0/76**
- Unsafe BLOCK: **76/76**
- Clean PASS: **32/32**
- Clean BLOCK: **0/32**
- Post-repair forensic audit: **PASS**
- Second-order relational audit: **PASS**
- Provider-model mismatch test: **PASS (rejected)**
- Reused provider response-ID test: **PASS (rejected)**
- Forged manifest-quality test: **PASS (rejected)**

## Remaining non-technical evidence boundary

SignalLock still cannot cryptographically prove a human reviewer identity or obtain a cryptographically signed OpenAI response receipt. Reviewer metadata and provider response IDs are audit/process evidence. Final claims must describe them that way.

## Promotion decision

**Promote qualification tooling to v0.9. Do not claim V7 multilingual model quality yet.** The next legitimate promotion still requires the genuine human-reviewed Hindi/Telugu holdout and a fresh live 24/24 provider-backed run under this exact frozen runtime/model.
