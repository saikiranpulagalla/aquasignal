# AquaSignal

## Verified Freshwater Risk Communication

**AI may rewrite the warning. It may not rewrite the protective action.**

AquaSignal is a **Track 6 — Resilience Informatics** prototype for the OneAquaHealth IEEE Global Hackathon 2026. It is a last-mile integrity gateway for AI-assisted freshwater risk communication: an environmental/public-health officer supplies an authoritative advisory, an AI or human may simplify or shorten it for citizens, and AquaSignal independently checks whether **ACTION · PLACE · TIME · AUDIENCE · CONSTRAINT** survived before human approval.

> AquaSignal does **not** decide that water is unsafe. Upstream environmental systems and human experts retain that authority. AquaSignal begins after an advisory exists.

## The failure AquaSignal is built to catch

| | Message |
|---|---|
| **Authoritative advisory** | Visitors must avoid contact with Stream A **after 18:00**. |
| **Citizen-facing rewrite** | Visitors must avoid contact with Stream A **before 18:00**. |
| **Naive text similarity** | ~95% |
| **AquaSignal** | **CRITICAL DRIFT — AFTER → BEFORE** |

The rewrite is fluent and almost identical to the source, but the operational instruction is reversed.

A second One Health example:

| | Message |
|---|---|
| **Source** | Keep **children and pets** away from Stream A until 18:00. |
| **Rewrite** | Keep **children** away from Stream A until 18:00. |
| **AquaSignal** | **CRITICAL DRIFT — audience `pets` missing** |

## Why this belongs in OneAquaHealth

OneAquaHealth already provides environmental/citizen-science tools, including the Resilience Map, that turn freshwater observations into useful context for researchers and decision-makers. AquaSignal extends that ecosystem at the communication boundary:

```text
OneAquaHealth environmental context
        ↓
Resilience Map CSV / environmental OAH-FHIR JSON
        ↓
human environmental authority
        ↓
authoritative freshwater advisory
        ↓
SOURCE READINESS GATE
        ↓
AI/manual simplification or channel adaptation
        ↓
DETERMINISTIC FRESHWATER EXTRACTION
        ↓
AQUA SEMANTIC POLICY
        ↓
SIGNALLOCK VERIFICATION CORE
        ↓
PRESERVED / REVIEW / CRITICAL DRIFT
        ↓
human decision
        ↓
machine-readable integrity receipt
```

The primary demo adapter accepts a **Resilience Map-style CSV export** as environmental provenance. A bounded environmental FHIR R4-subset JSON adapter is also included as an interoperability path. Neither adapter infers public-health risk from measurements.

## Trust model

AquaSignal deliberately separates four authorities:

1. **Environmental evidence** — context/provenance only; AquaSignal does not invent thresholds or risk classifications.
2. **Human source authority** — the original advisory must pass a deterministic Source Readiness Gate before AquaSignal freezes it.
3. **AI proposal** — AI may propose citizen-facing wording but has **no verification authority**.
4. **Deterministic verification** — the supported English V1 PASS path uses the freshwater parser + explicit semantic policy + deterministic SignalLock comparator.

**The model that writes the message never gets to certify its own output.**

The source authority token is server-bound to the source text, extracted contract, environmental context, advisory ID, revision, and semantic profile. Changing any of them invalidates the old verification.

## Freshwater Protective Communication Profile v1

The prototype is intentionally narrow. Automatic PASS is limited to represented English constructs.

| Dimension | V1 examples |
|---|---|
| **ACTION** | avoid contact, do not touch/enter/swim/wade/fish/drink, boil water, keep away, restricted sample collection |
| **PLACE** | `Stream A`, `River A`, `Site A`, `Zone A`, `upstream of Bridge A`, `downstream of Bridge A` |
| **TIME** | before, after, until, at, starting at + explicit clock time |
| **AUDIENCE** | residents, visitors, children, pet owners, pets, swimmers, anglers, field staff, trained personnel |
| **CONSTRAINT** | strong vs advisory prohibition, `only`, quantitative boil duration |

Unsupported or unresolved operational language cannot receive automatic PASS. Relative time such as “this afternoon” deliberately fails closed because meaning depends on publication time. Negative `AND` coordination is also treated conservatively because its scope can be ambiguous.

## OneAquaHealth context adapters

### Resilience Map CSV — primary demo path

`POST /api/aqua/context/resilience-csv`

The adapter records:

- dataset SHA-256,
- one unambiguous site when available,
- date range,
- indicator column names,
- row/column provenance,
- explicit synthetic-vs-imported state.

It does **not** infer whether an indicator value is safe or unsafe.

### Environmental FHIR JSON — secondary path

`POST /api/aqua/context/fhir`

V1 accepts environmental `Observation` and `Location` resources only. It rejects patient resources. If a profile URI exactly matches the deployment-configured OAH allowlist, the API records that recognition but **does not claim FHIR certification or full OneAquaHealth IG conformance**.

## Human-review decisions

| UI | API | Meaning |
|---|---|---|
| **PRESERVED** | `PASS` | Represented meaning is preserved under the declared deterministic profile. Human approval is still required. |
| **REVIEW** | `REVIEW` | Verification is incomplete or ambiguous. AquaSignal refuses to guess. |
| **CRITICAL DRIFT** | `BLOCK` | A represented protective invariant changed, disappeared, or was added without authority. |

AquaSignal is **decision support**, not an autonomous publication gate.

## Validation snapshot

All numbers below describe bounded prototype evaluations, not safety certification.

| Evidence | Current result |
|---|---:|
| Inherited SignalLock unit/integration/regression suite | **611 / 611 passing** |
| AquaSignal-specific tests | **351 collected; requalification pending** |
| Combined automated suite | **962 collected; requalification pending** |
| Aqua DEV benchmark | **24 cases — 14 unsafe BLOCK · 0 unsafe PASS · 10 clean PASS** |
| Frozen Aqua holdout V17 | **73 cases — 40 unsafe BLOCK · 4 unsafe REVIEW · 3 SOURCE_REVIEW · 0 unsafe PASS · 26 clean PASS** |

### Why the release evidence is V17

AquaSignal deliberately burns frozen evidence whenever a sealed semantic/evaluator dependency changes. Early holdouts exposed real defects and were retained as historical evidence instead of being rewritten. V16 qualified under the v0.5.0 boundary, but the sixth reliability campaign intentionally changed sealed semantics to support unpunctuated list-item boundaries safely and to detect cross-directive relational rewiring. V16 therefore became stale by design.

V17 was authored with fresh cases only after that sixth campaign stabilized, sealed **before** any semantic execution, and executed exactly once. It is the current release evidence. It is **author-curated, not independent external validation**. It is sealed to:

- the dataset SHA-256,
- the semantic dependency fingerprint,
- the evaluator fingerprint,
- the exact runtime requirements lock,
- the Python runtime version.

`verify_release_evidence()` recomputes all V17 cases and requires the saved result to match exactly. Every declared critical mutation family must be 100% `BLOCK`; unsupported-source/candidate boundary cases may deliberately produce `SOURCE_REVIEW`/`REVIEW`; no unsafe case may receive `PASS`.

See [VALIDATION.md](VALIDATION.md) for the full gates, hashes, audit trail, and limitations. The sixth semantic campaign is documented in `docs/HARDENING_REPORT_v0.6.0.md`; the seventh operational/provenance campaign is documented in `docs/HARDENING_REPORT_v0.6.1.md`.

## Four judge-demo cases

| Source | Candidate | Expected |
|---|---|---|
| Visitors must avoid contact with Stream A **after 18:00**. | … **before 18:00**. | **CRITICAL DRIFT** |
| Keep **children and pets** away from Stream A until 18:00. | Keep **children** away… | **CRITICAL DRIFT** |
| Avoid direct contact **downstream** of Bridge A… | … **upstream** of Bridge A… | **CRITICAL DRIFT** |
| Avoid direct contact until **6 PM**. | Do not touch the water until **18:00**. | **PRESERVED** |

A fifth adversarial case demonstrates hallucinated “helpful” advice: adding `Boil the water before drinking` to a contact-only source is treated as a new unauthorized operational action.

## Run locally

Requires Python **3.13.5** for the release-qualified build. V17 evidence is sealed to Python 3.13.5; broader Python compatibility is not claimed for this release.

```bash
git clone <your-aquasignal-repository-url>
cd aquasignal-oneaquahealth
python -m venv .venv
```

Activate it, then choose either the simple install or the pinned release environment.

### Simple development install

```bash
python -m pip install --no-build-isolation -e ".[dev]"
python scripts/release_gate.py
python -m apps.aqua_api
```

Open `http://127.0.0.1:8000`.

### Pinned release environment

```bash
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps --no-build-isolation -e .
python scripts/release_gate.py
python -m apps.aqua_api
```

For a wheel in a restricted/offline build environment with the pinned local build toolchain already installed:

```bash
make wheel
# equivalent: python -m pip wheel . --no-deps --no-build-isolation -w dist
```

No API key is needed for the deterministic demo. `OPENAI_API_KEY` is optional and only enables **proposal-only** rewrite generation.

## Docker

```bash
docker build -t aquasignal .
docker run --rm -p 8000:8000 \
  -e AQUASIGNAL_AUTHORITY_SECRET="replace-with-at-least-32-random-bytes-1234567890" \
  aquasignal
```

The app honors `PORT` (default `8000`). Configure a stable `AQUASIGNAL_AUTHORITY_SECRET` for a deployment that must preserve authority tokens across restarts. The Dockerfile is included and has been reviewed for required runtime assets; Docker execution itself was not verified in this audit environment because a Docker daemon/CLI was unavailable.

## Reproduce evidence

```bash
# All automated release gates, including recomputation/binding of frozen V17 evidence
python scripts/release_gate.py

# Developer-visible Aqua corpus
python scripts/run_aqua_benchmark.py

# Recompute and verify the frozen V17 release evidence against its sealed dataset/runtime
python scripts/verify_aqua_holdout.py

# Inherited SignalLock benchmark
python scripts/run_benchmark.py
```

`run_aqua_holdout.py` is retained for audit reproducibility. V17 is the current executed and frozen release evidence; any sealed semantic/evaluator/runtime-lock change invalidates it and requires a new holdout version rather than refreshing V17.

## API surface

| Endpoint | Purpose |
|---|---|
| `GET /api/aqua/health` | product/profile health |
| `GET /api/aqua/profile` | declared supported semantic scope |
| `GET /api/aqua/demo-context` | clearly labeled synthetic demo context |
| `POST /api/aqua/context/resilience-csv` | import environmental CSV provenance |
| `POST /api/aqua/context/fhir` | bounded environmental FHIR R4-subset context import |
| `POST /api/aqua/authority` | Source Readiness + context alignment + signed authority |
| `POST /api/aqua/verify` | deterministic candidate verification + integrity receipt |
| `POST /api/aqua/rewrite` | optional AI wording proposal; never verification authority |
| `GET /api/aqua/dev-benchmark` | developer-visible Aqua benchmark |
| `GET /api/aqua/release-evidence` | recomputed frozen V17 evidence status |

Interactive FastAPI documentation is available at `/docs`.

## Repository map

```text
aquasignal/               New OneAquaHealth domain layer
  domain/                 Context + deterministic freshwater profile
  integrity/              Context-bound authority, Aqua verifier, receipt
  evaluation/             Aqua DEV cases and metrics
  providers/              Proposal-only rewrite provider
apps/aqua_api/             AquaSignal FastAPI product surface
web_aqua/                  Judge-facing accessible UI
data/aqua/                 Synthetic context + frozen Aqua evaluation data
tests/aqua/                Aqua semantic/API/context/security tests
scripts/*aqua*             Aqua benchmark, holdout, evidence tooling

signallock/                Pre-existing generic integrity engine lineage
apps/api/, web/, tests/*   Preserved inherited SignalLock regression surface
```

The inherited files are retained so AquaSignal can continuously prove that the underlying integrity engine did not regress during the domain adaptation.

## Reuse disclosure

AquaSignal is **not presented as a from-scratch rewrite of SignalLock**. The generic SignalLock integrity engine predates this OneAquaHealth adaptation. The new Aqua-specific product layer, freshwater profile, context adapters, authority binding, Aqua semantic policy, evaluation corpora, UI, API, receipts, documentation, and release tooling are separated and disclosed explicitly.

Read [docs/REUSE_DISCLOSURE.md](docs/REUSE_DISCLOSURE.md) before submission.

## Limits

- Research/hackathon prototype; not a public-health authority or safety certification.
- English V1 only for automatic PASS.
- No autonomous environmental-risk inference.
- No claim of full OneAquaHealth FHIR IG conformance or FHIR certification.
- Named-site grammar is deliberately bounded; unsupported natural language fails closed.
- The Aqua holdouts are author-curated, not independent external evaluations.
- A PASS means preservation under implemented checks, **not permission to publish without human review**.
- Production deployment needs broader ecological/linguistic qualification, operational governance, shared state where relevant, and independent validation.

## Hackathon alignment

**Track 6 — Resilience Informatics.** AquaSignal complements early-warning and resilience systems by protecting the final communication step between environmental intelligence and citizen action. It is designed as an integration gateway rather than another water-quality dashboard or predictor.

OneAquaHealth references used for the product boundary:

- [OneAquaHealth IEEE Global Hackathon](https://www.oneaquahealth.eu/oneaquahealth-ieee-global-hackathon/) — tracks, requirements, practical/scalable focus
- [OneAquaHealth Resilience Map](https://www.oneaquahealth.eu/2026/05/11/oneaquahealth-resilience-map-exploring-environmental-health-through-data/) — environmental data exploration and CSV export
- [OneAquaHealth Project Solutions](https://www.oneaquahealth.eu/project-solutions/) — Resilience Map, GEOSSIP, DSS ecosystem
- [OneAquaHealth Informatics, Technology & Standards](https://www.oneaquahealth.eu/oneaquahealth-ieee-global-hackathon-informatics-technology-standards/) — interoperability/FAIR/FHIR context

## Documentation

- [Hackathon submission copy](docs/HACKATHON_SUBMISSION.md)
- [Architecture and trust boundaries](docs/ARCHITECTURE.md)
- [Freshwater Safety Contract / profile](docs/SAFETY_CONTRACT.md)
- [Validation evidence](VALIDATION.md)
- [Reuse disclosure](docs/REUSE_DISCLOSURE.md)
- [3–5 minute demo script](docs/DEMO_SCRIPT.md)
- [Final release report](docs/FINAL_RELEASE_REPORT.md)
- [Publish/deploy checklist](docs/PUBLISH_CHECKLIST.md)

## License

MIT. See [LICENSE](LICENSE).
