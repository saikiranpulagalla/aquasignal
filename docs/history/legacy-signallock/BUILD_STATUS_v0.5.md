# SignalLock AI v0.5 — Third-Order Hardening Status

## Promotion status

**V0–V6 regression/hardening gates: PASS.**

**V7 tooling: hardened, but LIVE multilingual qualification remains NOT EXECUTED.**

**V8 submission: LOCKED until a newly authored, independently reviewed, sealed V7 holdout passes.**

## Verified in this build

- Automated test suite: **156/156 PASS**.
- Controlled DEV benchmark: **108/108 expected decisions**.
  - unsafe PASS: **0/76**
  - unsafe BLOCK: **76/76**
  - clean PASS: **32/32**
- Post-repair forensic audit: **PASS**.
- Second-order audit: **PASS** with no unsafe text PASS and no CAP unsafe PASS.
- Third-order regression family now permanently covers:
  - OR-group rebinding;
  - independent sequence-chain rebinding;
  - advised/urged/can modality weakening/strengthening;
  - multiple temporal constraints;
  - unsupported imperatives (`head to`, `disconnect`);
  - open-vocabulary named areas and audience groups;
  - Hindi/Telugu AVOID and DRINK clean cases;
  - Hindi modality/time semantic contradiction;
  - CAP description mutation, info reordering, category ordering and polygon rotation;
  - V7 unsafe BLOCK-recall gate;
  - external packaged-release trust anchor.

## Third-order outcomes

- Unsafe English transformations: **12/12 BLOCK**.
- Legitimate English semantic rewrites: **4/4 PASS**.
- Correct Hindi/Telugu AVOID/DRINK structured candidates: **4/4 PASS**.
- Hindi exact-evidence modality/time semantic lie: **BLOCK**.
- CAP material description change: **BLOCK**.
- CAP harmless equivalences (info reorder/category reorder/polygon rotation): **3/3 PASS**.

## Architectural changes

1. Directive relations are now verified as a graph: OR-group membership and sequence chains are compared independently of sentence-local IDs.
2. Actions support multiple temporal constraints while retaining backward-compatible legacy deadline/operator fields.
3. Unknown deontic language no longer defaults to MUST; advisory/permission forms are typed.
4. English extraction captures additional imperatives plus open-vocabulary modal-governed audiences and named areas.
5. Hindi/Telugu native guard independently validates supported action/object, modality and temporal direction instead of only action keywords.
6. CAP info blocks are semantically matched instead of positionally matched; unordered categories and equivalent polygon rotations are canonicalized; description changes are checked.
7. V7 requires unsafe BLOCK recall, author diversity overall and per fault family, and mixed clean+unsafe secondary review.
8. The contaminated v0.4 V7 packet is retired. Active v0.5 challenge seeds are fresh and the packet builder rejects seeds already present in development/test code.
9. Packaged releases require an external `SIGNALLOCK_TRUSTED_RUNTIME_SHA256` anchor; editing code and self-resealing the manifest no longer yields `clean=true` without that external digest.
10. Public live-provider mode requires a stable `SIGNALLOCK_AUTHORITY_SECRET`; browser live authentication uses a same-origin HttpOnly session cookie after token exchange.
11. Any candidate/source/language/provider mutation immediately renders the prior verdict **STALE** and clears old signals.

## Intentionally not claimed

- No real OpenAI multilingual V7 run was performed in this environment.
- No human Hindi/Telugu authoring/review evidence is fabricated.
- v0.5 is qualification-ready tooling, not a completed V7 certification.
