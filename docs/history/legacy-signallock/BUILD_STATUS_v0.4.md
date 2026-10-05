# SignalLock build status — v0.4 V7 qualification-ready

## Promotion status

**V0–V6: PASS / re-earned.**

**V7 tooling and qualification protocol: PASS.**

**V7 live multilingual model-quality result: BLOCKED on external evidence, not failed.** This package deliberately does not manufacture API execution or human review.

## What changed after v0.3

1. Added a fixed **24-case V7 authoring plan**: 12 Hindi + 12 Telugu; 6 clean + 6 unsafe per language; each critical relational fault family represented once per language.
2. Clean cases use fresh official IMD guidance. Unsafe cases use fresh compositional V7 sources that are not copied from the DEV benchmark.
3. Split qualification into separate roles/stages: candidate author, source-authority reviewer, blinded primary reviewer, and distinct second reviewer for unsafe cases.
4. Blinded review templates omit `target_decision`, `fault_class`, authoring instructions, and author identity.
5. Finalization refuses reviewer disagreement instead of silently correcting labels after the fact.
6. Strict V7 sealer now rejects source contracts with no operational directives or unresolved operational text.
7. Strict V7 sealer enforces author/reviewer independence even if helper scripts are bypassed.
8. Candidate-language validation now requires both Unicode-script evidence and an independent Hindi/Telugu lexical/morphological cue.
9. V7 preflight reports qualification-kit state separately from sealed-holdout state.
10. Package release identity no longer falsely reuses the parent Git commit after post-package hardening; the v0.4 package is identified by its immutable release ID + runtime-tree SHA-256.

## Verified in this environment

- Automated tests: **149 / 149 PASS**
- Controlled DEV benchmark: **108 / 108 expected outcomes**
  - unsafe: **0 / 76 PASS**, **76 / 76 BLOCK**
  - clean: **32 / 32 PASS**
- Post-repair forensic audit: **PASS**
- Second-order adversarial audit: **PASS**
  - 12 / 12 targeted unsafe relational cases BLOCK
  - 4 / 4 targeted safe semantic rewrites PASS
  - 0 / 7 CAP material changes PASS
  - authority tamper rejected
  - exact-evidence multilingual semantic contradiction -> REVIEW
- V7 qualification-kit regression tests: PASS
  - exact 24-case balanced plan
  - target labels hidden from blinded reviewers
  - primary disagreement rejected
  - empty authority oracle rejected
  - script-only/non-Hindi Devanagari case rejected

## Current V7 blockers

The remaining blockers are intentionally external:

1. `OPENAI_API_KEY` is not available in this execution environment, so no real live multilingual structured extraction is claimed.
2. The 24 Hindi/Telugu candidate rows have not been authored/reviewed by independent humans, so there is no legitimate sealed holdout yet.

The current authoring packet is therefore **planned-valid-awaiting-human-work**, not "V7 passed".

## Correct next execution sequence

```bash
python scripts/prepare_v7_qualification_kit.py
export OPENAI_API_KEY='...'
export OPENAI_MODEL='gpt-5.6-luna'
python scripts/fill_v7_authority_drafts.py
# human authority review + candidate authoring -> data/multilingual/v7_authored.jsonl
python scripts/prepare_v7_blind_reviews.py data/multilingual/v7_authored.jsonl
# independent humans complete primary/secondary review files
python scripts/finalize_v7_reviews.py data/multilingual/v7_authored.jsonl data/multilingual/v7_primary_review.jsonl data/multilingual/v7_secondary_review.jsonl
python scripts/seal_v7_holdout.py data/multilingual/v7_reviewed.jsonl
python scripts/run_v7_preflight.py
python scripts/run_v7_multilingual.py
```

Do not unlock V8 or claim multilingual safety/accuracy until the final V7 runner exits 0 on a genuinely sealed reviewed holdout.
