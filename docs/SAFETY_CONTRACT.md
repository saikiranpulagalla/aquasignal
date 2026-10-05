# AquaSignal Freshwater Protective Communication Profile v1

AquaSignal converts the authoritative advisory and candidate rewrite into the inherited typed `SafetyContract`, then adds freshwater-specific deterministic policy. The profile is intentionally bounded: unsupported meaning routes to human review instead of being guessed equivalent.

## Preservation dimensions

### ACTION

Supported protective predicates include:

- avoid direct contact / do not touch water,
- do not enter,
- do not swim,
- do not wade,
- do not fish,
- do not drink,
- boil water before drinking,
- keep supported audiences away,
- restricted sample collection.

Candidate-only supported actions are treated as unauthorized additions.

### PLACE

Supported place forms include simple named scopes such as `Stream A`, `River A`, `Creek A`, `Site A`, and `Zone A`, plus `upstream of <landmark>` and `downstream of <landmark>`.

Freshwater policy adds two invariants absent from generic prose normalization:

1. single-letter identifiers are meaningful (`Stream A` ≠ `Stream B`);
2. `UPSTREAM` ≠ `DOWNSTREAM` for the same landmark.

### TIME

Supported explicit relations:

- `UNTIL`,
- `BEFORE`,
- `AFTER`,
- `AT`,
- `STARTING [AT]`.

Clock equivalence uses the inherited normalizer (`6 PM` ↔ `18:00`). Relative expressions such as `this afternoon`, `tonight`, and `tomorrow` are unresolved in V1 because they depend on publication time.

### AUDIENCE

V1 recognizes:

- residents,
- visitors,
- children,
- pet owners,
- pets,
- swimmers,
- anglers,
- field staff,
- trained personnel.

Audience deletion or unauthorized addition is compared bidirectionally.

### CONSTRAINT / FORCE

Positive `MUST`/`SHOULD`/`MAY` distinctions are inherited from SignalLock. Negative directives require an Aqua-specific force tag because the shared schema represents them under the common `PROHIBITED` modality.

AquaSignal therefore distinguishes:

- strong prohibition: imperative `avoid`, `do not`, `must not`, `never`;
- advisory prohibition: `should avoid`, `should not`.

Strong ↔ advisory changes are P0 critical drift.

`only trained personnel` is represented as a bound restrictive tag so deletion of `only` is observable.

## Quantity

V1 uses quantities only for supported boil-duration guidance. `at least 1 minute` is represented as a boil-duration quantity, not a generic “water depth” quantity. This explicitly fixes a domain bug discovered during adaptation.

AquaSignal does not infer chemical/pathogen thresholds from environmental measurements.

## Supported coordination

V1 supports a two-verb negative `OR` coordination such as:

`Do not swim or fish in Stream A.`

Order is symmetric. Negative `AND` coordination is intentionally unresolved because natural-language negation can make its scope ambiguous.

## Source Readiness

The source is ready only when:

- English V1 applies,
- at least one supported protective action is extracted,
- no operational source clause remains unresolved,
- any comparable context/site relationship is not a deterministic mismatch.

Failure produces `SOURCE_REVIEW`; AquaSignal does not mint a clean authority token for an unresolved source.

## Verdict semantics

- `PASS / PRESERVED`: represented invariants match under the declared profile.
- `REVIEW`: no confirmed critical drift, but representation or comparison is incomplete.
- `BLOCK / CRITICAL DRIFT`: a represented critical invariant changed/disappeared/appeared without authority.

All three remain subordinate to final human review.
