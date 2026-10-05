# AquaSignal publication and submission checklist

## Do not invalidate the frozen evidence

The current Aqua holdout V17 is bound to the semantic/evaluator/runtime dependencies declared in `data/aqua/holdout_v17.manifest.json`.

Before submission:

- **Do not modify** any dependency sealed by `data/aqua/holdout_v17.manifest.json` unless you are prepared to treat V17 as burned and create a new frozen holdout version. This includes freshwater extraction/verifier logic, shared schema/normalization/verifier dependencies, Aqua evaluation code, and the pinned runtime lock.
- Run `python scripts/verify_aqua_holdout.py` after any merge/rebase.
- Run `python scripts/release_gate.py` on the exact public repository checkout.

## Publish as a new repository

Recommended repository name:

`aquasignal-oneaquahealth`

Suggested GitHub description:

`Verified AI-assisted freshwater risk communication for OneAquaHealth Track 6 — deterministic ACTION · PLACE · TIME · AUDIENCE · CONSTRAINT integrity checks before human approval.`

Suggested topics:

`oneaquahealth`, `one-health`, `freshwater`, `resilience`, `ai-safety`, `fastapi`, `human-in-the-loop`, `semantic-integrity`, `hackathon`

Keep the public repository separate from the original SignalLock repository. Preserve `docs/REUSE_DISCLOSURE.md`.

## Git publication sequence

From the final extracted folder:

```bash
git init
git add .
git commit -m "AquaSignal OneAquaHealth v0.6.1"
git branch -M main
git remote add origin <new-public-repository-url>
git push -u origin main
```

Then clone the public repository into a clean directory and run:

```bash
python -m venv .venv
# activate environment
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps --no-build-isolation -e .
python scripts/release_gate.py
python -m apps.aqua_api
```

Record the final public commit SHA in the Devpost submission. `RELEASE_MANIFEST.json` intentionally has `source_commit: null` because this artifact was prepared before the new repository existed; do not invent a commit SHA retroactively.

After the qualified release gate, build the final source archive and wheel, then regenerate the release manifest with their real paths:

```bash
python scripts/build_aqua_release_manifest.py \
  --source-archive <final-source-archive> \
  --wheel <final-wheel>
```

The tool records only a real checkout's `HEAD` commit and an exact tag at that commit, when present. It records SHA-256 values for the supplied archive and wheel; absent artifacts and non-Git source trees remain `null` rather than being inferred.

## Deployment

Configure at minimum:

```text
AQUASIGNAL_ENV=production
AQUASIGNAL_AUTHORITY_SECRET=<stable high-entropy secret, at least 32 bytes>
```

Optional proposal-only AI rewrite (disabled by default):

```text
AQUASIGNAL_REWRITE_ENABLED=true
AQUASIGNAL_REWRITE_TOKEN=<separate deployment token, at least 32 bytes>
OPENAI_API_KEY=<server-side key>
OPENAI_MODEL=<model>
```

The deterministic demo does not require an AI key.

After deployment verify:

- `/api/aqua/health`
- `/api/aqua/release-evidence`
- homepage loads CSS/JS
- synthetic demo context loads
- AFTER→BEFORE returns CRITICAL DRIFT
- 6 PM→18:00 returns PRESERVED
- audience loss returns CRITICAL DRIFT
- downstream→upstream returns CRITICAL DRIFT
- receipt downloads

## Screenshots/video

Use `docs/SCREENSHOT_CAPTURE.md` and `docs/DEMO_SCRIPT.md`.

Record the demo from the deployed/public release, not the inherited `web/` SignalLock interface.

## Rules/reuse record

Keep any organizer response clarifying reuse of participant-authored pre-existing open-source components. The repository already discloses the exact pre-existing/new boundary in `docs/REUSE_DISCLOSURE.md`.

## Devpost final checks

- Track 6 — Resilience Informatics is visible near the top.
- Problem, primary user and One Health impact are concrete.
- Public repository URL works without authentication.
- Working prototype URL works in an incognito browser.
- 3–5 minute video uses the frozen release.
- Validation numbers match `VALIDATION.md` and `RELEASE_MANIFEST.json`.
- Historical burned holdouts are not hidden or misrepresented; V17 is the only current release evidence.
- No claim of environmental-risk inference, FHIR certification, safety certification, or independent external Aqua validation.
- Synthetic demo data is visibly labeled.
- Human publication authority remains explicit.
