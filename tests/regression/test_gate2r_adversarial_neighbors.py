from __future__ import annotations

import pytest

from signallock.contracts.extractor import HeuristicExtractor
from signallock.contracts.schema import Certainty, Decision, Severity, TemporalOperator
from signallock.verification.engine import VerificationEngine


E = HeuristicExtractor()
V = VerificationEngine()


def verify(source: str, candidate: str):
    return V.verify(E.extract(source), E.extract(candidate))


@pytest.mark.parametrize(
    ("source", "candidate", "expected"),
    [
        ("A severe wildfire affects the eastern zone. Residents must evacuate.", "A moderate wildfire affects the eastern zone. Residents must evacuate.", Decision.BLOCK),
        ("A minor wildfire affects the eastern zone. Residents must evacuate.", "A severe wildfire affects the eastern zone. Residents must evacuate.", Decision.BLOCK),
        ("A severe wildfire affects the eastern zone. Residents must evacuate.", "A wildfire affects the eastern zone. Residents must evacuate.", Decision.BLOCK),
        ("A wildfire affects the eastern zone. Residents must evacuate.", "A severe wildfire affects the eastern zone. Residents must evacuate.", Decision.REVIEW),
    ],
)
def test_severity_mutations_never_pass(source: str, candidate: str, expected: Decision) -> None:
    assert verify(source, candidate).decision == expected


def test_severity_extraction_and_safe_surface_variation() -> None:
    source = E.extract("A SEVERE wildfire affects the eastern zone! Residents must evacuate.")
    candidate = E.extract("A severe wildfire affects the eastern zone. Residents must evacuate.")
    assert source.severity == candidate.severity == Severity.SEVERE
    assert V.verify(source, candidate).decision == Decision.PASS


@pytest.mark.parametrize(
    ("source", "candidate"),
    [
        ("A wildfire is likely to affect the eastern zone. Residents must evacuate.", "A wildfire is possible to affect the eastern zone. Residents must evacuate."),
        ("A wildfire is unlikely to affect the eastern zone. Residents must evacuate.", "A wildfire is observed to affect the eastern zone. Residents must evacuate."),
        ("A wildfire is likely to affect the eastern zone. Residents must evacuate.", "A wildfire affects the eastern zone. Residents must evacuate."),
    ],
)
def test_certainty_mutations_never_pass(source: str, candidate: str) -> None:
    assert verify(source, candidate).decision != Decision.PASS


def test_certainty_extraction_and_if_possible_is_not_misclassified() -> None:
    likely = E.extract("A wildfire is likely to affect the eastern zone. Residents must evacuate.")
    assert likely.certainty == Certainty.LIKELY
    possible_condition = E.extract("A wildfire affects the eastern zone. Residents should evacuate if possible.")
    assert possible_condition.certainty == Certainty.UNKNOWN
    assert V.verify(possible_condition, possible_condition).decision == Decision.PASS


@pytest.mark.parametrize(
    ("source_event", "candidate_event"),
    [
        ("radiation release", "dam failure"),
        ("toxic plume", "landslide"),
        ("building collapse", "power outage"),
    ],
)
def test_unrepresented_hazard_identities_fail_closed(source_event: str, candidate_event: str) -> None:
    source = f"A {source_event} affects the eastern zone. Residents must evacuate."
    candidate = f"A {candidate_event} affects the eastern zone. Residents must evacuate."
    result = verify(source, candidate)
    assert result.decision == Decision.REVIEW
    assert E.extract(source).unresolved_operational_text
    assert E.extract(candidate).unresolved_operational_text


def test_unknown_hazard_attached_to_parsed_action_is_not_covered_by_action_alone() -> None:
    source = "Residents must evacuate at 4 PM due to a radiation release."
    candidate = "Residents must evacuate at 4 PM due to a dam failure."
    assert verify(source, candidate).decision == Decision.REVIEW


@pytest.mark.parametrize(
    ("source", "candidate"),
    [
        ("Residents must evacuate at 6 AM.", "Residents must evacuate at 9 AM."),
        ("Residents must evacuate at 18:00.", "Residents must evacuate at 20:00."),
        ("Residents must evacuate starting at noon.", "Residents must evacuate starting at 3 PM."),
        ("Residents must evacuate on Monday.", "Residents must evacuate on Tuesday."),
        ("Residents must evacuate on 25 September.", "Residents must evacuate on 26 September."),
        ("Residents must evacuate from 4 PM.", "Residents must evacuate from 8 PM."),
        ("Residents must evacuate starting Friday.", "Residents must evacuate starting Saturday."),
    ],
)
def test_new_temporal_families_change_cannot_pass(source: str, candidate: str) -> None:
    assert verify(source, candidate).decision == Decision.BLOCK


def test_temporal_operators_are_structured_not_string_hacks() -> None:
    at = E.extract("Residents must evacuate at 18:00.").required_actions[0]
    starting = E.extract("Residents must evacuate starting Friday.").required_actions[0]
    on = E.extract("Residents must evacuate on 25 September.").required_actions[0]
    assert at.temporal_constraints[0].operator == TemporalOperator.AT
    assert starting.temporal_constraints[0].operator == TemporalOperator.STARTING
    assert on.temporal_constraints[0].operator == TemporalOperator.ON
    assert on.temporal_constraints[0].time == "25 September"


def test_exact_time_normalization_preserves_safe_equivalence() -> None:
    assert verify("Residents must evacuate at noon.", "Residents must evacuate at 12 PM.").decision == Decision.PASS
    assert verify("Residents must evacuate at 6 PM.", "Residents must evacuate at 6 p.m.").decision == Decision.PASS


def test_relative_time_is_fail_closed_when_not_normalized() -> None:
    source = E.extract("Residents must evacuate tonight.")
    candidate = E.extract("Residents must evacuate tomorrow.")
    assert source.unresolved_operational_text
    assert candidate.unresolved_operational_text
    assert V.verify(source, candidate).decision != Decision.PASS


@pytest.mark.parametrize(
    ("source", "candidate"),
    [
        ("Residents must evacuate when sirens sound.", "Residents must evacuate when officials call."),
        ("Residents must evacuate when sirens sound.", "Residents must evacuate."),
        ("Residents must evacuate.", "Residents must evacuate when sirens sound."),
        ("Residents must evacuate whenever sirens sound.", "Residents must evacuate whenever officials call."),
        ("Residents must evacuate provided that sirens sound.", "Residents must evacuate provided that officials call."),
        ("Residents must evacuate as long as sirens sound.", "Residents must evacuate as long as officials call."),
    ],
)
def test_condition_mutations_cannot_pass(source: str, candidate: str) -> None:
    assert verify(source, candidate).decision == Decision.BLOCK


def test_whether_is_not_flattened_into_unconditional_action() -> None:
    source = E.extract("Residents must evacuate whether sirens sound or not.")
    assert source.required_actions
    assert source.required_actions[0].condition is None
    assert source.unresolved_operational_text
    assert V.verify(source, source).decision == Decision.REVIEW


def test_existing_if_negation_behavior_remains_blocking() -> None:
    result = verify("Residents must evacuate if sirens sound.", "Residents must evacuate if sirens do not sound.")
    assert result.decision == Decision.BLOCK


@pytest.mark.parametrize("relation", ["before", "after", "until", "by"])
def test_existing_temporal_relations_still_preserve_and_detect_changes(relation: str) -> None:
    same = verify(f"Residents must evacuate {relation} 6 PM.", f"Residents must evacuate {relation} 6 p.m.")
    changed = verify(f"Residents must evacuate {relation} 6 PM.", f"Residents must evacuate {relation} 8 PM.")
    assert same.decision == Decision.PASS
    assert changed.decision == Decision.BLOCK


def test_existing_alias_temporal_relations_still_work() -> None:
    assert verify("Residents must evacuate no later than 6 PM.", "Residents must evacuate by 6 PM.").decision == Decision.PASS
    assert verify("Residents must evacuate prior to 6 PM.", "Residents must evacuate before 6 PM.").decision == Decision.PASS


def test_safe_controls_remain_passable() -> None:
    assert verify("Residents must evacuate.", "Residents must evacuate.").decision == Decision.PASS
    assert verify("Residents MUST evacuate!", "Residents must evacuate.").decision == Decision.PASS
    assert verify("Residents must shelter indoors.", "Residents must stay indoors.").decision == Decision.PASS
    assert verify("Extreme heat affects the eastern zone. Residents must shelter indoors.", "Extreme heat affects the eastern zone. Residents must stay indoors.").decision == Decision.PASS
    assert verify("A severe storm affects the eastern zone. Residents must shelter indoors.", "A severe storm affects the eastern zone. Residents must stay indoors.").decision == Decision.PASS


@pytest.mark.parametrize(
    ("source", "candidate"),
    [
        ("A severe wildfire affects the eastern zone. Residents must evacuate.", "A minor wildfire affects the eastern zone. Residents must evacuate."),
        ("A wildfire is likely to affect the eastern zone. Residents must evacuate.", "A wildfire is unlikely to affect the eastern zone. Residents must evacuate."),
        ("Residents must evacuate at 6 AM.", "Residents must evacuate at 9 AM."),
        ("Residents must evacuate before 6 PM.", "Residents must evacuate after 6 PM."),
        ("Residents must evacuate when sirens sound.", "Residents must evacuate."),
        ("Residents must evacuate when sirens sound.", "Residents must evacuate when officials call."),
        ("Residents must evacuate due to a radiation release.", "Residents must evacuate."),
    ],
)
def test_gate2r_metamorphic_safety_changes_never_preserve_pass(source: str, candidate: str) -> None:
    assert verify(source, candidate).decision != Decision.PASS


def test_unrepresented_severity_modifier_on_parsed_action_forces_review() -> None:
    source = "Residents must evacuate under severe conditions."
    candidate = "Residents must evacuate under minor conditions."
    assert E.extract(source).unresolved_operational_text
    assert E.extract(candidate).unresolved_operational_text
    assert verify(source, candidate).decision == Decision.REVIEW
