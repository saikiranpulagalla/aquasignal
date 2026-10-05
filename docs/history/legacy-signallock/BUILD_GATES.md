# SignalLock gated build status — v0.3 relational hardening

| Version | Gate | Status | Evidence / blocker |
|---|---|---|---|
| V0 | Contract/schema foundation | **PASS (re-earned)** | Scoped directive fields, modality, temporal operators, logic/sequence, schema consistency |
| V1 | CAP ingestion/verification | **PASS for implemented strict profile** | CAP 1.2 namespace/dateTime checks + envelope/all-info/geospatial comparison; larger external real-alert corpus still desirable |
| V2 | Safety Contract extraction | **PASS offline / live multilingual qualification pending** | Relation-aware English extractor; Unicode normalization with original offsets; live structured provider is provenance checked + independent native semantic guard |
| V3 | Transform engine | **PASS offline / live provider pending** | Simplify/SMS regression green; live translation requires credentials and V7 evidence |
| V4 | Verification engine | **PASS strengthened DEV + second-order audit** | One-to-one relational action matching; 12/12 previously missed unsafe relationship attacks now BLOCK |
| V5 | Fault benchmark | **PASS strengthened DEV** | 108 cases: 76 unsafe / 32 clean; **0 unsafe PASS, 76 BLOCK, 32 clean PASS** |
| V6 | Demo/API boundary | **PASS regression** | Server-sealed authority, whole-CAP verifier, stale-response suppression, live-provider auth/rate guard, CSP/escaping |
| V7 | Frozen multilingual holdout | **IMPLEMENTED, LIVE BLOCKED** | Strict language-script validation, reviewer metadata, diversity/fault coverage, model/config/prompt/schema binding, resumable retries, fail-closed process exit. Real sealed Hindi/Telugu run still requires independent reviewed data + `OPENAI_API_KEY` |
| V8 | Submission package/video | **LOCKED until V7** | Do not claim multilingual production/safety metrics before real V7 passes |

## Re-earned second-order gates

The v0.3 regression audit requires all of these simultaneously:

- relational unsafe PASS rate: **0% target, <=5% aggregate maximum**
- action↔area swaps: **0 PASS**
- action↔audience swaps: **0 PASS**
- quantity/exception binding swaps: **0 PASS**
- deontic/modality reversal: **0 PASS**
- temporal-operator reversal: **0 PASS**
- logic/sequence reversal: **0 PASS**
- authority-contract tampering: **0 PASS**
- model evidence/semantic contradiction: **0 PASS**
- CAP envelope/geospatial material changes: **0 PASS**
- targeted clean scoped paraphrases: **>=80% PASS** and **<=10% BLOCK**
- unresolved semantic relation: **REVIEW, never PASS**

Run:

```bash
pytest -q
python scripts/run_benchmark.py
python scripts/run_postrepair_audit.py
python scripts/run_second_order_audit.py
```

## V7 preflight

`python scripts/run_v7_preflight.py` is a real CI-style gate: when `ready_to_execute_v7=false`, the command exits non-zero. A packaged release may prove immutable identity via `RELEASE_MANIFEST.json`; a Git checkout must be clean. A failed V7 metric gate also exits non-zero after persisting the report.
