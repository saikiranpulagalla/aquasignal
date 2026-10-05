from __future__ import annotations

from collections import Counter
import re

from signallock.contracts.normalization import normalize_time_string
from signallock.contracts.schema import Decision, SafetyContract, VerificationResult, VerificationSignal
from signallock.verification.engine import VerificationEngine

from aquasignal.domain.freshwater import aqua_canonical_place, aqua_exact_duration_seconds


_RELATIVE_AREA = re.compile(r"\b(?P<rel>upstream|downstream)\s+of\s+(?P<landmark>.+)$", re.I)
_NAMED_AREA = re.compile(r"^(?P<kind>stream|river|creek|site|zone)\s+(?P<name>.+)$", re.I)

def _relative_area(value: str) -> tuple[str, str] | None:
    match = _RELATIVE_AREA.search(value.strip())
    if not match:
        return None
    return match.group("rel").casefold(), aqua_canonical_place(match.group("landmark"))


def _named_area(value: str) -> tuple[str, str] | None:
    match = _NAMED_AREA.match(value.strip())
    if not match:
        return None
    return match.group("kind").casefold(), aqua_canonical_place(value)


def _all_areas(contract: SafetyContract) -> list[str]:
    out = list(contract.affected_areas)
    for action in contract.required_actions + contract.prohibited_actions:
        out.extend(action.scoped_areas)
    return list(dict.fromkeys(out))


def _aqua_force(action) -> str | None:
    return next((x for x in action.bound_exceptions if x.startswith("aqua-force:")), None)


def _force_match_key(action) -> tuple:
    return (
        action.verb.casefold().strip(),
        (action.object or "").casefold().strip(),
        tuple(sorted(a.casefold().strip() for a in action.scoped_audience)),
        tuple(sorted(aqua_canonical_place(a) for a in action.scoped_areas)),
        tuple(sorted((t.operator.value, normalize_time_string(t.time)) for t in action.temporal_constraints)),
    )


def _predicate_scope_key(action) -> tuple:
    return (
        action.type.value,
        action.verb.casefold().strip(),
        (action.object or "").casefold().strip(),
        tuple(sorted(a.casefold().strip() for a in action.scoped_audience)),
        tuple(sorted(aqua_canonical_place(a) for a in action.scoped_areas)),
    )


def _relational_binding_components(action) -> tuple[tuple, tuple, tuple, tuple]:
    """Canonical dimensions used to detect cross-directive rewiring.

    Each individual dimension may be preserved globally while its association with a
    different directive changes.  Comparing marginals plus the complete binding lets
    AquaSignal distinguish a harmless clause reorder from a time/site/audience swap.
    """
    predicate = (
        action.type.value,
        action.verb.casefold().strip(),
        (action.object or "").casefold().strip(),
        bool(action.negated),
        action.modality.value,
        tuple(sorted(" ".join(x.casefold().split()) for x in action.bound_exceptions)),
    )
    audience = tuple(sorted(" ".join(x.casefold().split()) for x in action.scoped_audience))
    areas = tuple(sorted(aqua_canonical_place(x) for x in action.scoped_areas))
    temporal = tuple(sorted((x.operator.value, normalize_time_string(x.time)) for x in action.temporal_constraints))
    return predicate, audience, areas, temporal


def _cross_directive_rewire(source: SafetyContract, candidate: SafetyContract) -> bool:
    if candidate.unresolved_operational_text:
        return False
    source_actions = source.required_actions + source.prohibited_actions
    candidate_actions = candidate.required_actions + candidate.prohibited_actions
    if len(source_actions) < 2 or len(source_actions) != len(candidate_actions):
        return False

    source_bindings = [_relational_binding_components(action) for action in source_actions]
    candidate_bindings = [_relational_binding_components(action) for action in candidate_actions]
    if Counter(source_bindings) == Counter(candidate_bindings):
        return False

    # A rewire is provable only when every dimension is preserved as a multiset and
    # *only the cross-action association changed*.  If any marginal changed, leave the
    # case to the ordinary verifier instead of manufacturing certainty.
    for index in range(4):
        if Counter(binding[index] for binding in source_bindings) != Counter(
            binding[index] for binding in candidate_bindings
        ):
            return False
    return True


def _binding_summary(contract: SafetyContract) -> str:
    rows = []
    for action in contract.required_actions + contract.prohibited_actions:
        predicate, audience, areas, temporal = _relational_binding_components(action)
        rows.append(
            f"{predicate[1]}"
            f"[aud={','.join(audience) or '-'};area={','.join(areas) or '-'};"
            f"time={','.join(f'{op}:{time}' for op, time in temporal) or '-'}]"
        )
    return "; ".join(sorted(rows))[:1200]


def _append_once(signals: list[VerificationSignal], signal: VerificationSignal) -> None:
    key = (signal.field, signal.status, signal.expected, signal.observed, signal.detector)
    if not any((s.field, s.status, s.expected, s.observed, s.detector) == key for s in signals):
        signals.append(signal)


def _downgrade_source_mismatch_when_candidate_unresolved(
    signals: list[VerificationSignal], candidate: SafetyContract
) -> list[VerificationSignal]:
    """Avoid false certainty when candidate language is outside the deterministic profile.

    The generic verifier correctly reports structural source facts as missing when the
    candidate extractor produced no corresponding structure.  If candidate text also
    contains unresolved operational language, however, that absence may mean either
    true omission *or* an unsupported paraphrase.  AquaSignal must REVIEW that case,
    not claim confirmed drift.  Explicitly parsed additions/contradictions remain FAIL.
    """
    if not candidate.unresolved_operational_text:
        return signals
    uncertain_source_fields = {
        "required_action", "prohibited_action", "quantity", "affected_area",
        "audience", "exception",
    }
    out: list[VerificationSignal] = []
    for signal in signals:
        downgrade = (
            signal.status == "FAIL"
            and signal.field in uncertain_source_fields
            and not signal.field.startswith("candidate_only_")
        )
        # Named-site absence is likewise uncertain only when the extractor found no
        # candidate named site.  A parsed different identifier remains a hard FAIL.
        if (
            signal.status == "FAIL"
            and signal.field == "place_identifier"
            and signal.observed == "<missing>"
        ):
            downgrade = True
        if downgrade:
            out.append(signal.model_copy(update={
                "status": "UNKNOWN",
                "reason": (
                    "Candidate contains unresolved operational language; the source fact "
                    "cannot be distinguished from an unsupported paraphrase, so AquaSignal "
                    "requires REVIEW instead of asserting confirmed drift."
                ),
                "detector": "aqua_unresolved_candidate_policy",
            }))
        else:
            out.append(signal)
    return out


class AquaVerificationEngine:
    """Freshwater semantic policy around the proven SignalLock verifier.

    The wrapper adds domain invariants that the generic verifier cannot safely infer,
    especially flow-direction and exact named-site identifiers. Generic directive,
    timing, audience, modality, quantity and addition/deletion logic remains delegated
    to SignalLock.
    """

    def __init__(self) -> None:
        self._core = VerificationEngine()

    def verify(self, source: SafetyContract, candidate: SafetyContract) -> VerificationResult:
        base = self._core.verify(source, candidate)
        signals = list(base.signals)

        src_areas = _all_areas(source)
        cand_areas = _all_areas(candidate)
        src_rel = [x for x in (_relative_area(v) for v in src_areas) if x]
        cand_rel = [x for x in (_relative_area(v) for v in cand_areas) if x]

        # Multi-directive rewiring can preserve every individual verb/site/time token
        # while changing which constraint belongs to which action.  When all marginal
        # dimensions are identical but the action bindings differ, the relation change
        # is independently provable and therefore P0 drift rather than REVIEW.
        if _cross_directive_rewire(source, candidate):
            _append_once(signals, VerificationSignal(
                field="relational_binding", status="FAIL", criticality="P0",
                expected=_binding_summary(source),
                observed=_binding_summary(candidate),
                reason="Cross-directive action/site/time/audience bindings were reassigned while their global values were preserved.",
                detector="aqua_cross_directive_binding_policy",
            ))

        # A flow direction is operational meaning in freshwater advisories. Reversal
        # for the same landmark is P0 critical drift. A changed landmark is likewise a
        # critical place change rather than an ambiguous free-text relation.
        for srel, slandmark in src_rel:
            exact = {(crel, clandmark) for crel, clandmark in cand_rel}
            if (srel, slandmark) in exact:
                continue
            opposing = "upstream" if srel == "downstream" else "downstream"
            opposite = next(((crel, clandmark) for crel, clandmark in cand_rel if crel == opposing and clandmark == slandmark), None)
            if opposite:
                _append_once(signals, VerificationSignal(
                    field="place_relation", status="FAIL", criticality="P0",
                    expected=f"{srel.upper()} OF {slandmark}",
                    observed=f"{opposing.upper()} OF {slandmark}",
                    reason="Freshwater flow-direction relation reversed for the same landmark.",
                    detector="aqua_relative_location_policy",
                ))
                continue
            same_relation = next(((crel, clandmark) for crel, clandmark in cand_rel if crel == srel), None)
            if same_relation and same_relation[1] != slandmark:
                _append_once(signals, VerificationSignal(
                    field="place_relation", status="FAIL", criticality="P0",
                    expected=f"{srel.upper()} OF {slandmark}",
                    observed=f"{same_relation[0].upper()} OF {same_relation[1]}",
                    reason="Freshwater landmark changed within the same flow-direction relation.",
                    detector="aqua_relative_location_policy",
                ))

        # The shared SignalLock schema intentionally collapses all negative
        # directives into PROHIBITED. AquaSignal carries an internal force tag so a
        # strong prohibition cannot be weakened to advisory wording and receive only
        # an ambiguous REVIEW. Pair otherwise-identical prohibited actions and make
        # this freshwater-specific constraint explicit.
        cand_force_by_key = {_force_match_key(a): _aqua_force(a) for a in candidate.prohibited_actions}
        for action in source.prohibited_actions:
            source_force = _aqua_force(action)
            if not source_force:
                continue
            candidate_force = cand_force_by_key.get(_force_match_key(action))
            if candidate_force and candidate_force != source_force:
                _append_once(signals, VerificationSignal(
                    field="constraint_force", status="FAIL", criticality="P0",
                    expected=source_force.removeprefix("aqua-force:"),
                    observed=candidate_force.removeprefix("aqua-force:"),
                    reason="Freshwater prohibition strength was weakened or otherwise changed.",
                    detector="aqua_prohibition_force_policy",
                ))

        # A known relative/imprecise temporal phrase is deliberately represented
        # as UNKNOWN by the extractor. If it replaces a precise source clock on the
        # same directive, that is a confirmed weakening rather than generic parser
        # uncertainty, so keep a decisive BLOCK signal.
        candidate_by_predicate: dict[tuple, list] = {}
        for action in candidate.required_actions + candidate.prohibited_actions:
            candidate_by_predicate.setdefault(_predicate_scope_key(action), []).append(action)
        for action in source.required_actions + source.prohibited_actions:
            if not action.temporal_constraints:
                continue
            if any(t.operator.value == "UNKNOWN" for t in action.temporal_constraints):
                continue
            for observed in candidate_by_predicate.get(_predicate_scope_key(action), []):
                if any(t.operator.value == "UNKNOWN" for t in observed.temporal_constraints):
                    _append_once(signals, VerificationSignal(
                        field="time_precision", status="FAIL", criticality="P0",
                        expected=", ".join(f"{t.operator.value} {t.time}" for t in action.temporal_constraints),
                        observed=", ".join(t.time for t in observed.temporal_constraints),
                        reason="A precise freshwater time constraint was replaced by an imprecise relative expression.",
                        detector="aqua_temporal_precision_policy",
                    ))
                    break

        # Aqua boil-duration evidence is compared exactly in Decimal space. The
        # inherited schema stores floats, which can collapse adjacent large integer
        # literals to the same binary value. This policy prevents a float precision
        # collision from producing PASS while preserving safe unit equivalence.
        source_durations = [q for q in source.quantities if (q.meaning or "").casefold() == "boil duration"]
        candidate_durations = [q for q in candidate.quantities if (q.meaning or "").casefold() == "boil duration"]
        if len(source_durations) == 1 and len(candidate_durations) == 1:
            source_exact = aqua_exact_duration_seconds(source_durations[0])
            candidate_exact = aqua_exact_duration_seconds(candidate_durations[0])
            if source_exact is not None and candidate_exact is not None and source_exact != candidate_exact:
                _append_once(signals, VerificationSignal(
                    field="quantity_precision", status="FAIL", criticality="P0",
                    expected=str(source_exact) + " seconds",
                    observed=str(candidate_exact) + " seconds",
                    reason="Exact freshwater boil-duration magnitude changed.",
                    detector="aqua_exact_duration_policy",
                ))

        # Preserve identifiers such as Stream A / Site A exactly. The generic
        # SignalLock canonicalizer drops English articles, which is correct for prose
        # but unsafe when "A" is an identifier token.
        src_named = [x for x in (_named_area(v) for v in src_areas) if x]
        cand_named = [x for x in (_named_area(v) for v in cand_areas) if x]
        for skind, svalue in src_named:
            if any(ckind == skind and cvalue == svalue for ckind, cvalue in cand_named):
                continue
            same_kind = [cvalue for ckind, cvalue in cand_named if ckind == skind]
            _append_once(signals, VerificationSignal(
                field="place_identifier", status="FAIL", criticality="P0",
                expected=svalue,
                observed=", ".join(same_kind) if same_kind else "<missing>",
                reason="Named freshwater site identifier changed or disappeared.",
                detector="aqua_named_site_policy",
            ))

        signals = _downgrade_source_mismatch_when_candidate_unresolved(signals, candidate)

        confirmed = [s.field for s in signals if s.status == "FAIL" and s.criticality in {"P0", "P1"}]
        uncertain = [s.field for s in signals if s.status in {"WARN", "UNKNOWN"}]
        if confirmed:
            decision = Decision.BLOCK
            summary = "Freshwater protective meaning changed. Human review required before publication."
        elif uncertain:
            decision = Decision.REVIEW
            summary = "No confirmed critical drift, but freshwater verification is incomplete or uncertain. Human review required."
        else:
            decision = Decision.PASS
            summary = "Supported freshwater protective meaning is preserved; final human approval is still required."
        return VerificationResult(
            decision=decision,
            signals=signals,
            critical_failures=list(dict.fromkeys(confirmed)),
            warnings=list(dict.fromkeys(uncertain)),
            summary=summary,
            source_contract=source,
            candidate_contract=candidate,
        )
