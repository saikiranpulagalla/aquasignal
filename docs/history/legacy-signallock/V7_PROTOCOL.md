# V7 Multilingual Holdout Protocol — hardened

V7 is the first stage allowed to produce multilingual evidence for a SignalLock submission. Development benchmark numbers are not substitutes for this protocol.

## Objective

Measure whether SignalLock preserves useful approvals while intercepting dangerous semantic changes in **Hindi (`hi`) and Telugu (`te`)** on a frozen, independently reviewed holdout that was not used to tune prompts, rules, thresholds, canonical labels, or extraction heuristics.

## Non-negotiable controls

1. Freeze runtime code before sealing. A clean Git identity or an intact `RELEASE_MANIFEST.json` runtime-tree hash is required.
2. Every authoritative English `source_contract` is human reviewed, provenance validated, non-empty at the operational-directive layer, free of unresolved operational text, stored in the row, and never re-extracted during scoring.
3. Candidate language is independently validated with two deterministic signals: Unicode script coverage plus a Hindi/Telugu lexical/morphological cue; a JSON label alone cannot establish Hindi/Telugu.
4. Every row records candidate `author_id`, source-authority review metadata, blinded `reviewer_id`, timezone-aware `reviewed_at`, `source_reference`, and `fault_class`. The candidate author may not review their own row.
5. Every expected-BLOCK row requires a **different** `second_reviewer_id`; the second reviewer must differ from both the candidate author and primary reviewer.
6. Blinded review sheets use unrelated opaque IDs, omit descriptive task IDs/source references/hidden labels, and are independently shuffled; a private integrity map binds each verdict to the exact source/candidate content shown.
7. The strict sealer rejects duplicate/near-duplicate case padding and enforces source/candidate/fault-class diversity.
8. Required fault coverage is: `clean`, `action_area`, `action_audience`, `quantity_exception_binding`, `modality`, `temporal`, and `logic_sequence`.
9. The seal binds the exact provider, model ID, fixed provider configuration, extraction-system-prompt hash, and structured-schema hash.
10. Provider/transient failures are retried in bounded fashion, checkpointed per case, and ultimately scored as `REVIEW`; they are never omitted.
11. Every successful live case stores the exact post-provider candidate `SafetyContract`, its SHA-256, and a provider response receipt (response ID/model/timestamp/usage plus raw structured-output hash).
12. After the run, offline replay must reproduce every saved verifier decision, warning/failure list, aggregate metric, and final gate from the sealed source contracts plus stored candidate contracts.
13. V8 remains locked until the replay receipt matches the unchanged V7 result hash and the V7 gate passed with zero provider errors and zero checkpoint recovery.
14. The preflight and runner return non-zero process status when their gate is not satisfied.
15. If code/prompt/model configuration changes after results are inspected, retire the split to development and create a fresh holdout.
16. `PASS` means “contract preserved, ready for human review,” never “safe to publish autonomously.”

## Minimum enforced composition

- >= **24 rows total**
- Hindi and Telugu: >= **12 rows each**
- each language: >= **4 expected PASS** and >= **6 expected BLOCK**
- >= **6 unique authoritative source texts** overall; >=4 per language
- >= **12 unique candidate texts** overall; >=8 per language
- all seven required fault classes represented; every unsafe required class has >=2 independently authored cases
- at least two reviewer identities represented

A stronger final target remains 32–48 genuinely independent cases.

## Final row fields

In addition to the base fields, strict V7 requires:

```text
case_id
source_text
source_language
source_contract
candidate_text
candidate_language
expected_decision
human_reviewed: true
reviewer_id
reviewed_at
source_reference
fault_class
second_reviewer_id   # required and distinct for expected BLOCK
second_reviewed_at    # timezone-aware; required for expected BLOCK
```

## Human authoring/review before sealing

Use `docs/V7_REVIEW_WORKFLOW.md`. The recommended path is a fixed 24-case authoring packet, real source-contract drafts, human authority review, human candidate authoring, blinded primary review, and a distinct blinded second review for unsafe cases. Reviewer disagreement retires/replaces the case; it is never edited into agreement.

## Seal and run

```bash
export OPENAI_MODEL='gpt-5.6-luna'   # or freeze the exact intended model
python scripts/seal_v7_holdout.py data/multilingual/v7_reviewed.jsonl
python scripts/run_v7_preflight.py
export OPENAI_API_KEY='...'
python scripts/run_v7_multilingual.py
python scripts/verify_v7_evidence.py
python scripts/check_v8_unlock.py
```

`run_v7_multilingual.py` already performs replay verification immediately after writing the result; the standalone verifier exists for later independent re-checks. The exact model used at run time must match the sealed model fingerprint. Provider receipts are audit metadata rather than a cryptographic attestation from the provider.

## V7 gate

Overall:

- dangerous `PASS` rate on expected-BLOCK rows <= **5%**
- **zero PASS** in every required critical relational fault family
- clean `PASS` rate >= **80%**
- clean `BLOCK` rate <= **10%**
- exact decision accuracy >= **85%**

Per Hindi/Telugu language:

- >=12 cases
- >=4 expected-PASS rows
- >=6 expected-BLOCK rows
- dangerous `PASS` rate <=10%
- clean `PASS` rate >=70%

Numeric metrics alone cannot make the gate pass: diversity, reviewer, fault-class, language and runtime-binding evidence are mandatory.

## If V7 fails

Persist the report, keep the non-zero exit, move the failed split into development, diagnose/fix the failure class, freeze the new system, and obtain/seal a **new independent holdout**. Never relabel a failed holdout as successful.
