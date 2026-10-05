from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from enum import StrEnum

from signallock.contracts.normalization import canonical_text, normalize_time_string, quantities_equivalent
from signallock.contracts.schema import (
    Action,
    ActionType,
    Decision,
    LogicOperator,
    Modality,
    Quantity,
    SafetyContract,
    VerificationResult,
    VerificationSignal,
)


class Relation(StrEnum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"


_VERB_ALIASES = {
    "stay": "shelter", "remain": "shelter", "take shelter": "shelter", "leave": "evacuate",
    "keep out": "enter", "keep out of": "enter", "stay away": "approach", "stay away from": "approach",
}
_TEXT_WHOLE_ALIASES = {
    "motorists": "drivers",
    "driver": "drivers",
    "emergency staff": "emergency personnel",
    "emergency responders": "emergency personnel",
    "except for emergency personnel": "except emergency personnel",
    "unless you are emergency personnel": "except emergency personnel",
    "unless emergency personnel": "except emergency personnel",
    "if officials order it": "official-order",
    "if ordered by officials": "official-order",
    "only if officials order": "official-order",
}


def _lang_root(value: str) -> str:
    return (value or "").split("-")[0].casefold()


def _semantic_text(value: str | None) -> str:
    text = canonical_text(value)
    return _TEXT_WHOLE_ALIASES.get(text, text)


def _canon_verb(value: str | None) -> str:
    text = _semantic_text(value)
    return _VERB_ALIASES.get(text, text)


def _text_relation(
    a: str | None,
    b: str | None,
    *,
    source_language: str = "en",
    candidate_language: str = "en",
) -> Relation:
    ca, cb = _semantic_text(a), _semantic_text(b)
    if not ca and not cb:
        return Relation.MATCH
    if not ca or not cb:
        return Relation.MISMATCH
    if ca == cb:
        return Relation.MATCH
    # A lexical scope negation must never be treated as a fuzzy paraphrase.
    if ca.startswith("non-") != cb.startswith("non-"):
        return Relation.MISMATCH

    direction_tokens = {"north", "south", "east", "west", "northeast", "northwest", "southeast", "southwest"}
    polarity_tokens = {"non", "not", "no", "without"}
    a_tokens, b_tokens = set(ca.split()), set(cb.split())
    if (a_tokens & direction_tokens) != (b_tokens & direction_tokens) and ((a_tokens | b_tokens) & direction_tokens):
        return Relation.MISMATCH
    if (a_tokens & polarity_tokens) != (b_tokens & polarity_tokens) and ((a_tokens | b_tokens) & polarity_tokens):
        return Relation.MISMATCH
    if re.findall(r"[+-]?\d+(?:\.\d+)?", ca) != re.findall(r"[+-]?\d+(?:\.\d+)?", cb):
        return Relation.MISMATCH
    # Named operational scopes such as Zone A/Zone B must not become fuzzy UNKNOWN.
    za = re.findall(r"\bzone\s+([a-z0-9-]+)\b", ca)
    zb = re.findall(r"\bzone\s+([a-z0-9-]+)\b", cb)
    if (za or zb) and za != zb:
        return Relation.MISMATCH

    if _lang_root(source_language) == _lang_root(candidate_language):
        if SequenceMatcher(None, ca, cb).ratio() >= 0.80:
            return Relation.UNKNOWN
        return Relation.MISMATCH
    return Relation.UNKNOWN


_COND_Q = re.compile(
    r"(?P<prefix>.*?)(?P<rel>more\s+than|greater\s+than|above|over|less\s+than|below|under|at\s+least|at\s+most)\s+"
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>cm|mm|m|meters?|metres?|centimeters?|centimetres?|millimeters?|millimetres?)(?P<suffix>.*)",
    re.I,
)


def _rel_word(value: str) -> str:
    value = " ".join(value.casefold().split())
    if value in {"more than", "greater than", "above", "over"}:
        return ">"
    if value in {"less than", "below", "under"}:
        return "<"
    if value == "at least":
        return ">="
    if value == "at most":
        return "<="
    return value


def _condition_relation(a: str | None, b: str | None, *, source_language: str, candidate_language: str) -> Relation:
    basic = _text_relation(a, b, source_language=source_language, candidate_language=candidate_language)
    if basic == Relation.MATCH or not a or not b:
        return basic
    if _lang_root(source_language) != _lang_root(candidate_language):
        return basic
    ma, mb = _COND_Q.search(a.casefold()), _COND_Q.search(b.casefold())
    if ma and mb:
        if _rel_word(ma.group("rel")) != _rel_word(mb.group("rel")):
            return Relation.MISMATCH
        if not quantities_equivalent(float(ma.group("value")), ma.group("unit"), float(mb.group("value")), mb.group("unit")):
            return Relation.MISMATCH
        sa = canonical_text(ma.group("prefix") + " " + ma.group("suffix"))
        sb = canonical_text(mb.group("prefix") + " " + mb.group("suffix"))
        if sa == sb or SequenceMatcher(None, sa, sb).ratio() >= 0.84:
            return Relation.MATCH
    return basic


def _match_string_lists(expected: list[str], observed: list[str], *, source_language: str, candidate_language: str) -> Relation:
    if not expected and not observed:
        return Relation.MATCH
    if len(expected) != len(observed):
        return Relation.MISMATCH
    used: set[int] = set()
    saw_unknown = False
    for exp in expected:
        match_idx = None
        unknown_idx = None
        for idx, obs in enumerate(observed):
            if idx in used:
                continue
            rel = _text_relation(exp, obs, source_language=source_language, candidate_language=candidate_language)
            if rel == Relation.MATCH:
                match_idx = idx
                break
            if rel == Relation.UNKNOWN and unknown_idx is None:
                unknown_idx = idx
        chosen = match_idx if match_idx is not None else unknown_idx
        if chosen is None:
            return Relation.MISMATCH
        if match_idx is None:
            saw_unknown = True
        used.add(chosen)
    return Relation.UNKNOWN if saw_unknown else Relation.MATCH


def _quantity_relation(exp: Quantity, obs: Quantity, *, source_language: str, candidate_language: str) -> Relation:
    if not quantities_equivalent(exp.value, exp.unit, obs.value, obs.unit):
        return Relation.MISMATCH
    if exp.relation != obs.relation:
        return Relation.MISMATCH
    return _text_relation(exp.meaning, obs.meaning, source_language=source_language, candidate_language=candidate_language)


def _match_quantity_lists(expected: list[Quantity], observed: list[Quantity], *, source_language: str, candidate_language: str) -> Relation:
    if len(expected) != len(observed):
        return Relation.MISMATCH
    used: set[int] = set()
    saw_unknown = False
    for exp in expected:
        exact = unknown = None
        for idx, obs in enumerate(observed):
            if idx in used:
                continue
            rel = _quantity_relation(exp, obs, source_language=source_language, candidate_language=candidate_language)
            if rel == Relation.MATCH:
                exact = idx
                break
            if rel == Relation.UNKNOWN and unknown is None:
                unknown = idx
        chosen = exact if exact is not None else unknown
        if chosen is None:
            return Relation.MISMATCH
        if exact is None:
            saw_unknown = True
        used.add(chosen)
    return Relation.UNKNOWN if saw_unknown else Relation.MATCH


def _action_relation(expected: Action, observed: Action, *, source_language: str, candidate_language: str) -> Relation:
    if expected.negated != observed.negated or expected.type != observed.type:
        return Relation.MISMATCH
    relations: list[Relation] = []

    ev, ov = _canon_verb(expected.verb), _canon_verb(observed.verb)
    if ev == ov:
        relations.append(Relation.MATCH)
    elif _lang_root(source_language) != _lang_root(candidate_language):
        relations.append(Relation.UNKNOWN)
    else:
        relations.append(Relation.MISMATCH)

    # Deontic strength is a first-class invariant.  MAY/SHOULD/MUST/NOT_REQUIRED
    # are not interchangeable even when the action predicate is identical.
    relations.append(Relation.MATCH if expected.modality == observed.modality else Relation.MISMATCH)

    for left, right in [(expected.object, observed.object), (expected.destination, observed.destination)]:
        relations.append(_text_relation(left, right, source_language=source_language, candidate_language=candidate_language))
    relations.append(_condition_relation(expected.condition, observed.condition, source_language=source_language, candidate_language=candidate_language))
    relations.append(_match_string_lists(expected.scoped_audience, observed.scoped_audience, source_language=source_language, candidate_language=candidate_language))
    relations.append(_match_string_lists(expected.scoped_areas, observed.scoped_areas, source_language=source_language, candidate_language=candidate_language))
    relations.append(_match_quantity_lists(expected.bound_quantities, observed.bound_quantities, source_language=source_language, candidate_language=candidate_language))
    relations.append(_match_string_lists(expected.bound_exceptions, observed.bound_exceptions, source_language=source_language, candidate_language=candidate_language))

    def temporal_key(action: Action) -> list[tuple[str, str]]:
        if action.temporal_constraints:
            return sorted((row.operator.value, normalize_time_string(row.time) or canonical_text(row.time)) for row in action.temporal_constraints)
        if action.deadline or action.temporal_operator:
            op = action.temporal_operator.value if action.temporal_operator else "UNKNOWN"
            return [(op, normalize_time_string(action.deadline or "") or canonical_text(action.deadline or ""))]
        return []
    relations.append(Relation.MATCH if temporal_key(expected) == temporal_key(observed) else Relation.MISMATCH)
    # Boolean-group and sequence membership are graph-level relations. Comparing local
    # indices/operators here would both miss rewiring and falsely reject equivalent
    # sentence splitting; they are checked after directive matching.

    if Relation.MISMATCH in relations:
        return Relation.MISMATCH
    if Relation.UNKNOWN in relations:
        return Relation.UNKNOWN
    return Relation.MATCH


def _directive_node_key(action: Action) -> tuple:
    """Semantic identity of a directive node, excluding inter-directive graph edges."""
    if action.temporal_constraints:
        temporal = tuple(sorted((x.operator.value, normalize_time_string(x.time) or canonical_text(x.time)) for x in action.temporal_constraints))
    elif action.deadline or action.temporal_operator:
        temporal = ((action.temporal_operator.value if action.temporal_operator else "UNKNOWN", normalize_time_string(action.deadline or "") or canonical_text(action.deadline or "")),)
    else:
        temporal = ()
    return (
        action.type.value, _canon_verb(action.verb), _semantic_text(action.object), _semantic_text(action.destination),
        action.modality.value, tuple(sorted(_semantic_text(x) for x in action.scoped_audience)),
        tuple(sorted(_semantic_text(x) for x in action.scoped_areas)), _semantic_text(action.condition),
        temporal, tuple(sorted((q.value, canonical_text(q.unit), q.relation.value, _semantic_text(q.meaning)) for q in action.bound_quantities)),
        tuple(sorted(_semantic_text(x) for x in action.bound_exceptions)), action.negated,
    )

def _or_group_signatures(contract: SafetyContract) -> list[tuple]:
    groups: dict[str, list[tuple]] = {}
    for action in contract.required_actions + contract.prohibited_actions:
        if action.logic_operator != LogicOperator.OR:
            continue
        group = action.logic_group or "__ungrouped_or__"
        groups.setdefault(group, []).append(_directive_node_key(action))
    return sorted(tuple(sorted(nodes, key=repr)) for nodes in groups.values())

def _sequence_signatures(contract: SafetyContract) -> list[tuple]:
    groups: dict[str, list[tuple[int, tuple]]] = {}
    for action in contract.required_actions + contract.prohibited_actions:
        if action.sequence_index is None:
            continue
        group = action.sequence_group or action.logic_group or "__ungrouped_sequence__"
        groups.setdefault(group, []).append((action.sequence_index, _directive_node_key(action)))
    return sorted(tuple(node for _, node in sorted(nodes, key=lambda x: x[0])) for nodes in groups.values())

def _check_relation_graph(source: SafetyContract, candidate: SafetyContract, signals: list[VerificationSignal]) -> None:
    for field, expected, observed in [
        ("logic_or_groups", _or_group_signatures(source), _or_group_signatures(candidate)),
        ("sequence_graph", _sequence_signatures(source), _sequence_signatures(candidate)),
    ]:
        signals.append(VerificationSignal(
            field=field, status="PASS" if expected == observed else "FAIL", criticality="P0",
            expected=repr(expected), observed=repr(observed),
            reason="Directive relationship graph preserved." if expected == observed else "Directive relationship graph was rewired or materially changed.",
            detector="directive_relation_graph",
        ))


def _action_target(action: Action) -> str:
    return _semantic_text(action.object or action.destination)


def _same_scope(a: Action, b: Action) -> bool:
    # Empty scope means global/unspecified, so it overlaps another empty scope.
    return (
        _match_string_lists(a.scoped_audience, b.scoped_audience, source_language="en", candidate_language="en") != Relation.MISMATCH
        and _match_string_lists(a.scoped_areas, b.scoped_areas, source_language="en", candidate_language="en") != Relation.MISMATCH
    )


def _internal_action_contradictions(contract: SafetyContract) -> list[str]:
    conflicts: list[str] = []
    for req in contract.required_actions:
        req_verb, req_target = _canon_verb(req.verb), _action_target(req)
        for pro in contract.prohibited_actions:
            if req_verb != _canon_verb(pro.verb) or not _same_scope(req, pro):
                continue
            pro_target = _action_target(pro)
            if req_target and pro_target and req_target != pro_target:
                continue
            conflicts.append(f"required={_render_action(req)} <> prohibited={_render_action(pro)}")

    # Domain-level mutually exclusive protective actions.  OR alternatives are not
    # contradictions, and conditional/differently scoped directives are left alone.
    strong = {Modality.MUST, Modality.SHOULD}
    for i, left in enumerate(contract.required_actions):
        for right in contract.required_actions[i + 1:]:
            if {left.type, right.type} != {ActionType.SHELTER, ActionType.EVACUATE}:
                continue
            if left.modality not in strong or right.modality not in strong:
                continue
            if left.condition or right.condition or left.logic_operator == LogicOperator.OR or right.logic_operator == LogicOperator.OR:
                continue
            if _same_scope(left, right):
                conflicts.append(f"mutually-exclusive={_render_action(left)} <> {_render_action(right)}")
    return conflicts


def _render_action(action: Action) -> str:
    bits = [action.modality.value, action.type.value, action.verb]
    if action.object:
        bits.append(action.object)
    if action.destination:
        bits.append(f"to={action.destination}")
    if action.scoped_audience:
        bits.append("audience=" + ",".join(action.scoped_audience))
    if action.scoped_areas:
        bits.append("areas=" + ",".join(action.scoped_areas))
    if action.condition:
        bits.append(f"condition={action.condition}")
    if action.temporal_constraints:
        bits.append("time=" + ",".join(f"{x.operator.value}:{x.time}" for x in action.temporal_constraints))
    elif action.temporal_operator or action.deadline:
        bits.append(f"time={action.temporal_operator.value if action.temporal_operator else 'UNKNOWN'}:{action.deadline or ''}")
    if action.bound_quantities:
        bits.append("quantities=" + ",".join(_render_quantity(q.value, q.unit, q.relation.value, q.meaning) for q in action.bound_quantities))
    if action.bound_exceptions:
        bits.append("exceptions=" + ",".join(action.bound_exceptions))
    if action.sequence_index is not None:
        bits.append(f"seq={action.sequence_index}")
    if action.logic_operator != LogicOperator.SINGLE:
        bits.append(f"logic={action.logic_operator.value}")
    if action.negated:
        bits.append("negated=true")
    return " | ".join(bits)


def _render_quantity(value, unit, relation="Unknown", meaning=None) -> str:
    out = f"{relation} {value:g} {unit}"
    if meaning:
        out += f" ({meaning})"
    return out


def _meaningful(contract: SafetyContract) -> bool:
    return any([
        contract.hazard is not None, contract.audience, contract.affected_areas,
        contract.required_actions, contract.prohibited_actions,
        contract.urgency.value != "Unknown", contract.severity.value != "Unknown", contract.certainty.value != "Unknown",
        contract.effective_at is not None, contract.expires_at is not None,
        contract.quantities, contract.exceptions, contract.unresolved_operational_text,
    ])


def _dt_equal(a: datetime, b: datetime) -> bool:
    def utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return utc(a) == utc(b)


@dataclass(slots=True)
class VerificationEngine:
    """Bidirectional fail-closed comparison of scoped safety directives."""

    def verify(self, source: SafetyContract, candidate: SafetyContract) -> VerificationResult:
        signals: list[VerificationSignal] = []

        source_conflicts = _internal_action_contradictions(source)
        if source_conflicts:
            signals.append(VerificationSignal(
                field="source_internal_contradiction", status="UNKNOWN", criticality="P0",
                expected="unambiguous authoritative directives", observed=" | ".join(source_conflicts),
                reason="Authoritative directives are mutually contradictory for the same scope; automated approval is unsafe.",
                detector="scoped_contract_consistency",
            ))
        candidate_conflicts = _internal_action_contradictions(candidate)
        if candidate_conflicts:
            introduced = not source_conflicts or set(candidate_conflicts) != set(source_conflicts)
            signals.append(VerificationSignal(
                field="candidate_internal_contradiction", status="FAIL" if introduced else "UNKNOWN", criticality="P0",
                expected="no new contradictory directives", observed=" | ".join(candidate_conflicts),
                reason="Transformation introduced contradictory scoped directives." if introduced else "Candidate preserves an unresolved source contradiction.",
                detector="scoped_contract_consistency",
            ))

        for which, contract in [("source", source), ("candidate", candidate)]:
            if contract.unresolved_operational_text:
                signals.append(VerificationSignal(
                    field=f"{which}_extraction_uncertainty", status="UNKNOWN", criticality="P0",
                    expected="all operational clauses independently normalized",
                    observed=" | ".join(contract.unresolved_operational_text),
                    reason=f"{which.title()} contains operational semantics that are unresolved or independently unverified.",
                    detector="extraction_coverage_gate",
                ))

        if not _meaningful(source):
            signals.append(VerificationSignal(
                field="source_coverage", status="UNKNOWN", criticality="P0", expected="authoritative operational facts", observed="<none extracted>",
                reason="Authoritative contract contains no verifiable operational facts; approval would fail open.", detector="coverage_gate",
            ))
        elif not _meaningful(candidate):
            signals.append(VerificationSignal(
                field="candidate_coverage", status="UNKNOWN", criticality="P0", expected="transformed operational facts", observed="<none extracted>",
                reason="Candidate extraction is empty/incomplete; transformation cannot be approved.", detector="coverage_gate",
            ))

        self._check_actions(source, candidate, source.required_actions, candidate.required_actions, "required_action", signals)
        self._check_actions(source, candidate, source.prohibited_actions, candidate.prohibited_actions, "prohibited_action", signals)
        _check_relation_graph(source, candidate, signals)
        self._check_quantities(source, candidate, signals)
        self._check_string_set(source, candidate, source.affected_areas, candidate.affected_areas, "affected_area", "P0", signals)
        self._check_exceptions(source, candidate, signals)
        self._check_string_set(source, candidate, source.audience, candidate.audience, "audience", "P1", signals)
        self._check_hazard(source, candidate, signals)
        self._check_enum("urgency", source.urgency.value, candidate.urgency.value, signals, criticality="P1")
        self._check_enum("severity", source.severity.value, candidate.severity.value, signals, criticality="P1")
        self._check_enum("certainty", source.certainty.value, candidate.certainty.value, signals, criticality="P1")
        self._check_datetime("effective_at", source.effective_at, candidate.effective_at, signals)
        self._check_datetime("expires_at", source.expires_at, candidate.expires_at, signals)

        confirmed = [s.field for s in signals if s.status == "FAIL" and s.criticality in {"P0", "P1"}]
        uncertain = [s.field for s in signals if s.status in {"WARN", "UNKNOWN"}]
        if confirmed:
            decision, summary = Decision.BLOCK, "Protective-action contract mismatch detected. Block transformation and require human review."
        elif uncertain:
            decision, summary = Decision.REVIEW, "No confirmed critical mismatch, but verification is incomplete or uncertain. Human review required."
        else:
            decision, summary = Decision.PASS, "Scoped protective directives preserved across checked invariants; ready for human review."
        return VerificationResult(
            decision=decision, signals=signals, critical_failures=list(dict.fromkeys(confirmed)), warnings=list(dict.fromkeys(uncertain)),
            summary=summary, source_contract=source, candidate_contract=candidate,
        )

    @staticmethod
    def _check_actions(source: SafetyContract, candidate: SafetyContract, expected: list[Action], observed: list[Action], field: str, signals: list[VerificationSignal]) -> None:
        used: set[int] = set()
        for exp in expected:
            exact = unknown = None
            for idx, obs in enumerate(observed):
                if idx in used:
                    continue
                relation = _action_relation(exp, obs, source_language=source.language, candidate_language=candidate.language)
                if relation == Relation.MATCH:
                    exact = idx
                    break
                if relation == Relation.UNKNOWN and unknown is None:
                    unknown = idx
            chosen = exact if exact is not None else unknown
            if chosen is not None:
                used.add(chosen)
                status = "PASS" if exact is not None else "UNKNOWN"
                signals.append(VerificationSignal(
                    field=field, status=status, criticality="P0", expected=_render_action(exp), observed=_render_action(observed[chosen]),
                    reason="Scoped directive preserved." if status == "PASS" else "Directive predicate aligns but at least one semantic slot is independently unresolved.",
                    detector="bidirectional_scoped_directive",
                ))
            else:
                signals.append(VerificationSignal(
                    field=field, status="FAIL", criticality="P0", expected=_render_action(exp),
                    observed="; ".join(_render_action(x) for x in observed) or "<missing>",
                    reason="A source scoped directive is missing, rebound to another scope, or materially changed.", detector="bidirectional_scoped_directive",
                ))
        for idx, obs in enumerate(observed):
            if idx not in used:
                signals.append(VerificationSignal(
                    field=f"candidate_only_{field}", status="FAIL", criticality="P0", expected="<no new operational directive>", observed=_render_action(obs),
                    reason="Transformation introduced a scoped operational directive not present in the authority.", detector="bidirectional_scoped_directive",
                ))

    @staticmethod
    def _check_quantities(source: SafetyContract, candidate: SafetyContract, signals: list[VerificationSignal]) -> None:
        used: set[int] = set()
        for exp in source.quantities:
            exact = unknown = None
            for idx, obs in enumerate(candidate.quantities):
                if idx in used:
                    continue
                rel = _quantity_relation(exp, obs, source_language=source.language, candidate_language=candidate.language)
                if rel == Relation.MATCH:
                    exact = idx
                    break
                if rel == Relation.UNKNOWN and unknown is None:
                    unknown = idx
            chosen = exact if exact is not None else unknown
            if chosen is not None:
                used.add(chosen)
                rel = Relation.MATCH if exact is not None else Relation.UNKNOWN
                signals.append(VerificationSignal(
                    field="quantity", status="PASS" if rel == Relation.MATCH else "UNKNOWN", criticality="P0",
                    expected=_render_quantity(exp.value, exp.unit, exp.relation.value, exp.meaning),
                    observed=_render_quantity(candidate.quantities[chosen].value, candidate.quantities[chosen].unit, candidate.quantities[chosen].relation.value, candidate.quantities[chosen].meaning),
                    reason="Critical numeric value/unit/relation preserved." if rel == Relation.MATCH else "Numeric value is equivalent but semantic meaning is unresolved.",
                    detector="relational_quantity",
                ))
            else:
                signals.append(VerificationSignal(
                    field="quantity", status="FAIL", criticality="P0", expected=_render_quantity(exp.value, exp.unit, exp.relation.value, exp.meaning),
                    observed=", ".join(_render_quantity(x.value, x.unit, x.relation.value, x.meaning) for x in candidate.quantities) or "<missing>",
                    reason="Critical numeric value/unit/relation/meaning changed or disappeared.", detector="relational_quantity",
                ))
        for idx, obs in enumerate(candidate.quantities):
            if idx not in used:
                signals.append(VerificationSignal(
                    field="candidate_only_quantity", status="FAIL", criticality="P0", expected="<no new critical quantity>",
                    observed=_render_quantity(obs.value, obs.unit, obs.relation.value, obs.meaning),
                    reason="Transformation introduced an unexplained critical quantity.", detector="relational_quantity",
                ))

    @staticmethod
    def _check_string_set(source: SafetyContract, candidate: SafetyContract, expected: list[str], observed: list[str], field: str, criticality: str, signals: list[VerificationSignal]) -> None:
        used: set[int] = set()
        for exp in expected:
            exact = unknown = None
            for idx, obs in enumerate(observed):
                if idx in used:
                    continue
                rel = _text_relation(exp, obs, source_language=source.language, candidate_language=candidate.language)
                if rel == Relation.MATCH:
                    exact = idx
                    break
                if rel == Relation.UNKNOWN and unknown is None:
                    unknown = idx
            chosen = exact if exact is not None else unknown
            if chosen is not None:
                used.add(chosen)
                status = "PASS" if exact is not None else "UNKNOWN"
                signals.append(VerificationSignal(
                    field=field, status=status, criticality=criticality, expected=exp, observed=observed[chosen],
                    reason=f"{field.replace('_', ' ').title()} preserved." if status == "PASS" else "Cross-language/free-text equivalence is uncertain.",
                    detector="bidirectional_canonical_text",
                ))
            else:
                signals.append(VerificationSignal(
                    field=field, status="FAIL", criticality=criticality, expected=exp, observed=", ".join(observed) or "<missing>",
                    reason=f"Source {field.replace('_', ' ')} changed or disappeared.", detector="bidirectional_canonical_text",
                ))
        for idx, obs in enumerate(observed):
            if idx not in used:
                signals.append(VerificationSignal(
                    field=f"candidate_only_{field}", status="FAIL", criticality=criticality, expected="<no new value>", observed=obs,
                    reason=f"Transformation introduced a new {field.replace('_', ' ')}.", detector="bidirectional_canonical_text",
                ))

    @staticmethod
    def _check_exceptions(source: SafetyContract, candidate: SafetyContract, signals: list[VerificationSignal]) -> None:
        VerificationEngine._check_string_set(source, candidate, [x.text for x in source.exceptions], [x.text for x in candidate.exceptions], "exception", "P1", signals)

    @staticmethod
    def _check_hazard(source: SafetyContract, candidate: SafetyContract, signals: list[VerificationSignal]) -> None:
        a = source.hazard.type if source.hazard else None
        b = candidate.hazard.type if candidate.hazard else None
        if not a and not b:
            return
        rel = _text_relation(a, b, source_language=source.language, candidate_language=candidate.language)
        status = "PASS" if rel == Relation.MATCH else ("UNKNOWN" if rel == Relation.UNKNOWN else "FAIL")
        signals.append(VerificationSignal(
            field="hazard", status=status, criticality="P1", expected=a or "<absent>", observed=b or "<absent>",
            reason="Hazard type preserved." if status == "PASS" else "Hazard type changed, disappeared, or is unresolved.", detector="hazard_type",
        ))
        if status == "PASS" and (source.hazard.description if source.hazard else None or candidate.hazard.description if candidate.hazard else None):
            da = source.hazard.description if source.hazard else None
            db = candidate.hazard.description if candidate.hazard else None
            drel = _text_relation(da, db, source_language=source.language, candidate_language=candidate.language)
            dstatus = "PASS" if drel == Relation.MATCH else ("UNKNOWN" if drel == Relation.UNKNOWN else "FAIL")
            signals.append(VerificationSignal(
                field="hazard_description", status=dstatus, criticality="P1", expected=da or "<absent>", observed=db or "<absent>",
                reason="Material hazard qualifier preserved." if dstatus == "PASS" else "Hazard description materially changed or could not be established.",
                detector="hazard_description_semantics",
            ))

    @staticmethod
    def _check_enum(field: str, expected: str, observed: str, signals: list[VerificationSignal], *, criticality: str) -> None:
        if expected == "Unknown" and observed == "Unknown":
            return
        if expected == "Unknown" and observed != "Unknown":
            status, reason = "UNKNOWN", f"Candidate introduced {field} not present in the source contract."
        elif expected != "Unknown" and observed == "Unknown":
            status, reason = "FAIL", f"Source {field} disappeared from the candidate contract."
        elif expected != observed:
            status, reason = "FAIL", f"{field.title()} materially changed."
        else:
            status, reason = "PASS", f"{field.title()} preserved."
        signals.append(VerificationSignal(field=field, status=status, criticality=criticality, expected=expected, observed=observed, reason=reason, detector="structured_enum"))

    @staticmethod
    def _check_datetime(field: str, expected: datetime | None, observed: datetime | None, signals: list[VerificationSignal]) -> None:
        if expected is None and observed is None:
            return
        if expected is None and observed is not None:
            status, reason = "UNKNOWN", f"Candidate introduced {field} not present in the source contract."
        elif expected is not None and observed is None:
            status, reason = "FAIL", f"Source {field} disappeared from the candidate contract."
        elif expected is not None and observed is not None and not _dt_equal(expected, observed):
            status, reason = "FAIL", f"{field} changed."
        else:
            status, reason = "PASS", f"{field} preserved."
        signals.append(VerificationSignal(
            field=field, status=status, criticality="P0", expected=expected.isoformat() if expected else "<absent>",
            observed=observed.isoformat() if observed else "<absent>", reason=reason, detector="normalized_datetime",
        ))
