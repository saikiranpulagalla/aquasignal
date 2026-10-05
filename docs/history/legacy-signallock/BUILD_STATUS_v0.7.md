# SignalLock v0.7 — V7 execution-integrity checkpoint

## Promotion status

**V0–V6 + V7 qualification tooling: PASS.**

**V7 multilingual model-quality qualification: NOT EXECUTED.** It still requires a real, independently human-authored/reviewed Hindi/Telugu holdout and a live provider-backed run.

## New execution-integrity controls

- Fresh certification runs refuse any pre-existing checkpoint by default.
- `--resume` is explicit and diagnostic-only; any checkpoint-recovered case makes the V7 gate fail.
- Checkpoints use format 2.0 and bind to the exact sealed case input plus provider/model/runtime/config execution binding.
- Duplicate/unknown/mismatched recovered cases are rejected.
- Any provider extraction error makes the V7 gate fail; zero provider-error cases are required.
- `live_executed_cases` and `checkpoint_recovered_cases` are reported explicitly.
- Existing V7 result files are never silently overwritten.
- Preflight detects stale default checkpoint/result artifacts and blocks a fresh certification run until they are archived/removed.

## Regression evidence

- Automated tests: **165/165 PASS**
- DEV benchmark: **108 cases**
- Unsafe PASS: **0/76**
- Unsafe BLOCK: **76/76**
- Clean PASS: **32/32**
- Post-repair forensic audit: **PASS**
- Second-order relational audit: **PASS**
- V7 execution-integrity focused tests: **PASS**

## Current gate

Do not promote to V8/submission until a **fresh all-live** V7 run completes with:

- sealed strict V7 holdout valid and runtime-bound;
- 24/24 cases live-executed in the certification run;
- 0 checkpoint-recovered cases;
- 0 provider-error cases;
- all existing V7 semantic thresholds passing.
