# V7 independent review workflow

This workflow exists so the model under test, the candidate author, and the final label cannot silently certify one another.

## Roles

- **Candidate author**: writes the Hindi/Telugu candidate for each assigned task. The author sees the hidden authoring target (`clean` or one fault family) and must introduce no extra changes.
- **Authority/primary reviewer**: checks the English source contract against the exact English source and then reviews the candidate *without seeing the target label/fault class*. This person must be different from the candidate author.
- **Secondary unsafe reviewer**: independently reviews every row intended to be unsafe, also blind to the target label/fault class. This person must be different from both the author and the primary reviewer.

The authority reviewer and primary reviewer may be the same human. This keeps the hackathon workflow practical while still preventing self-review. Unsafe rows always get a second independent reviewer.

## Stage 1 — create the frozen authoring plan

```bash
python scripts/prepare_v7_qualification_kit.py
```

This writes exactly 24 tasks:

- 12 Hindi + 12 Telugu
- 6 clean + 6 unsafe per language
- one unsafe task per critical fault family per language
- clean sources come from fresh official IMD guidance
- unsafe source sentences are fresh compositional V7 challenges not used in the DEV benchmark

No candidate text, review label, or reviewer identity is fabricated by this command.

## Stage 2 — create source-contract drafts with the real provider

```bash
export OPENAI_API_KEY='...'
export OPENAI_MODEL='gpt-5.6-luna'
python scripts/fill_v7_authority_drafts.py
```

A human must then inspect/correct each unique source contract and fill:

```text
authority_reviewer_id
authority_reviewed_at
authority_notes
```

Never mark a source contract reviewed merely because the extraction provider produced it.

## Stage 3 — human candidate authoring

For every row, a human candidate author fills:

```text
candidate_text
author_id
```

The author follows `authoring_instruction`. Clean rows must preserve meaning. Unsafe rows must introduce exactly the requested fault and no unrelated error.

## Stage 4 — produce blinded reviewer files

After every row has candidate text and an authority-reviewed source contract:

```bash
python scripts/prepare_v7_blind_reviews.py data/multilingual/v7_authored.jsonl
```

The generated reviewer files deliberately omit `target_decision`, `fault_class`, authoring instructions, descriptive task IDs, source references, and author metadata. Primary and secondary files use unrelated opaque IDs and independently shuffled order. The command also writes `data/multilingual/v7_blind_review_map.json`; **keep that mapping private and never give it to either reviewer**.

The reviewer fills only:

```text
reviewer_id
reviewed_at
verdict   # PASS / REVIEW / BLOCK
notes
```

## Stage 5 — consensus finalization

```bash
python scripts/finalize_v7_reviews.py \
  data/multilingual/v7_authored.jsonl \
  data/multilingual/v7_primary_review.jsonl \
  data/multilingual/v7_secondary_review.jsonl
```

Finalization uses the private blind-review mapping and refuses to continue if:

- a review row contains hidden label/task/source-reference fields;
- a reviewer-facing source/candidate text was edited after blinding;
- the private mapping does not match the exact authored packet;
- an author self-reviews, including trivial case/whitespace identity aliases;
- an unsafe row lacks a distinct second reviewer;
- a blinded reviewer disagrees with the hidden expected label;
- the source contract lacks reviewed provenance;
- primary/secondary review timestamps predate authority-contract review;
- Hindi/Telugu script validation fails;
- any required task/fault/language coverage is missing.

A disagreement is **not corrected in place**. Retire that case and replace it with a fresh independently authored case before sealing.

## Stage 6 — seal and execute

```bash
python scripts/seal_v7_holdout.py data/multilingual/v7_reviewed.jsonl
python scripts/run_v7_preflight.py
python scripts/run_v7_multilingual.py
```

Only the last command can produce V7 model-quality metrics, and it exits non-zero if the declared gate fails.
