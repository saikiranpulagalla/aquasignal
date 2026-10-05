# AquaSignal architecture

## Product boundary

AquaSignal verifies **communication integrity after environmental risk assessment**. It does not infer whether a freshwater observation is dangerous, does not set health thresholds, and does not autonomously publish warnings.

```text
ENVIRONMENTAL CONTEXT
Resilience Map CSV / environmental FHIR
        │
        ▼
Context Adapter
(hash + provenance, no risk inference)
        │
        ▼
HUMAN AUTHORITY
Authoritative freshwater advisory
        │
        ▼
Source Readiness Gate
        │
  unresolved? ── yes ──> SOURCE REVIEW
        │ no
        ▼
Aqua Authority Envelope
source + contract + context + advisory/revision + profile
        │
        ▼
AI / human channel adaptation
(proposal only)
        │
        ▼
Deterministic Freshwater Extractor
        │
        ▼
Aqua Semantic Policy
        │
        ▼
Inherited SignalLock Comparator
        │
   ┌────┼────┐
   ▼    ▼    ▼
 PASS REVIEW BLOCK
   │    │    │
   └────┴────┘
        ▼
Human decision
        │
        ▼
Integrity Receipt
```

## Trust boundaries

### 1. Environmental evidence is context, not authority to invent advice

The Resilience CSV adapter records site/date/indicator/provenance metadata. The FHIR adapter accepts only environmental `Observation` and `Location` resources. Neither adapter maps measurements to a health-risk class.

### 2. Source Readiness precedes verification

A source can become authority only when the deterministic freshwater profile extracts at least one supported protective action and leaves no unresolved operational clause. A source/context named-site mismatch also forces `SOURCE_REVIEW`.

### 3. Authority is server-bound

The HMAC authority token binds:

- SHA-256 of source text,
- full source `SafetyContract`,
- full normalized environmental context,
- environmental context SHA-256,
- advisory ID,
- advisory revision,
- semantic profile ID.

Changing any bound input invalidates the token.

### 4. AI cannot approve itself

`POST /api/aqua/rewrite` can ask an external model to propose wording. That provider is absent from the verification path. Candidate verification always uses the deterministic V1 freshwater extractor.

### 5. Domain semantic policy surrounds, rather than rewrites, SignalLock

AquaSignal keeps the mature SignalLock comparator intact and adds only freshwater facts the generic engine cannot infer safely:

- `UPSTREAM` and `DOWNSTREAM` are contradictory for the same landmark;
- exact named-site identifiers such as `Stream A` are preserved;
- a strong prohibition cannot silently weaken to advisory wording;
- explicit unsupported negative `AND` scope fails closed.

This minimizes regression risk while keeping the domain extension auditable.

## Context alignment

Context/advisory alignment is deliberately conservative:

- exact comparable named site → `MATCH`;
- different comparable named site → `MISMATCH` → source review;
- multi-site CSV, raw FHIR `Location/123`, or arbitrary non-comparable site label → `UNKNOWN`, retained as provenance without pretending to know equivalence.

## Staleness and versions

The browser invalidates results whenever source text, candidate text or context changes. Authority tokens also bind advisory revision, so an older verified candidate cannot silently survive a new advisory revision.

## Integrity receipt

Each completed verification returns hashes for context, source and candidate plus profile/version, decision, differences and warnings. The receipt is audit evidence; it is not a publication authorization or digital signature by an environmental authority.

## Security notes

- request-size limits,
- CSP with `frame-ancestors 'none'`,
- `X-Content-Type-Options: nosniff`,
- no arbitrary server-side URL fetch for FHIR context,
- restricted environmental FHIR resource types,
- authority HMAC,
- optional provider API key remains server-side.

For production, configure a stable `AQUASIGNAL_AUTHORITY_SECRET`, use normal deployment secret management, and add shared state/rate limiting appropriate to the hosting architecture.
