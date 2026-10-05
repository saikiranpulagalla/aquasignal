from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from signallock.contracts.extractor import HeuristicExtractor
from signallock.contracts.schema import Decision, TemporalOperator
from signallock.verification.engine import VerificationEngine


CLIENT = TestClient(app)
E = HeuristicExtractor()
V = VerificationEngine()


def verify(source: str, candidate: str):
    return V.verify(E.extract(source, source_id="source"), E.extract(candidate, source_id="candidate"))


def verify_api(source: str, candidate: str) -> dict:
    r = CLIENT.post(
        "/api/verify",
        json={
            "source_text": source,
            "candidate_text": candidate,
            "source_language": "en",
            "candidate_language": "en",
            "provider": "heuristic",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def verify_frozen(source: str, candidate: str) -> dict:
    auth = CLIENT.post(
        "/api/extract-authority",
        json={"text": source, "language": "en", "provider": "heuristic"},
    )
    assert auth.status_code == 200, auth.text
    data = auth.json()
    r = CLIENT.post(
        "/api/verify-contract",
        json={
            "source_text": source,
            "source_contract": data["source_contract"],
            "authority_token": data["authority_token"],
            "candidate_text": candidate,
            "candidate_language": "en",
            "provider": "heuristic",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def first_action(text: str):
    return E.extract(text).required_actions[0]


def test_g3a_f001_direct_route_blocks() -> None:
    body = verify_api(
        "At 6 PM, residents must evacuate Zone A.",
        "At 8 PM, residents must evacuate Zone A.",
    )
    assert body["decision"] == "BLOCK"
    assert body["source_contract"]["required_actions"][0]["temporal_operator"] == "AT"
    assert body["candidate_contract"]["required_actions"][0]["temporal_operator"] == "AT"


def test_g3a_f001_frozen_route_blocks() -> None:
    body = verify_frozen(
        "At 6 PM, residents must evacuate Zone A.",
        "At 8 PM, residents must evacuate Zone A.",
    )
    assert body["decision"] == "BLOCK"


def test_preposed_at_is_structured_by_extractor() -> None:
    action = first_action("At 6 PM, residents must evacuate Zone A.")
    assert action.temporal_operator == TemporalOperator.AT
    assert [(x.operator, x.time) for x in action.temporal_constraints] == [(TemporalOperator.AT, "6 PM")]


@pytest.mark.parametrize(
    ("source", "candidate"),
    [
        ("At 7 AM, residents must evacuate Zone A.", "At 9 AM, residents must evacuate Zone A."),
        ("At noon, residents must evacuate Zone A.", "At 3 PM, residents must evacuate Zone A."),
        ("On Friday, residents must evacuate Zone A.", "On Saturday, residents must evacuate Zone A."),
        ("On 25 September, residents must evacuate Zone A.", "On 26 September, residents must evacuate Zone A."),
        ("Starting at 4 PM, residents must evacuate Zone A.", "Starting at 8 PM, residents must evacuate Zone A."),
        ("From 4 PM, residents must evacuate Zone A.", "From 8 PM, residents must evacuate Zone A."),
        ("Before 6 PM, residents must evacuate Zone A.", "After 6 PM, residents must evacuate Zone A."),
        ("After 6 PM, residents must evacuate Zone A.", "Before 6 PM, residents must evacuate Zone A."),
        ("By 6 PM, residents must evacuate Zone A.", "By 8 PM, residents must evacuate Zone A."),
        ("Until 6 PM, residents must evacuate Zone A.", "Until 8 PM, residents must evacuate Zone A."),
    ],
)
def test_original_gate3a_temporal_siblings_cannot_pass(source: str, candidate: str) -> None:
    assert verify(source, candidate).decision != Decision.PASS


@pytest.mark.parametrize(
    ("text", "operator", "value"),
    [
        ("At 6 PM, residents must evacuate Zone A.", TemporalOperator.AT, "6 PM"),
        ("Starting at 4 PM, residents must evacuate Zone A.", TemporalOperator.STARTING, "4 PM"),
        ("From 4 PM, residents must evacuate Zone A.", TemporalOperator.STARTING, "4 PM"),
        ("On Friday, residents must evacuate Zone A.", TemporalOperator.ON, "Friday"),
        ("Before 6 PM, residents must evacuate Zone A.", TemporalOperator.BEFORE, "6 PM"),
        ("After 6 PM, residents must evacuate Zone A.", TemporalOperator.AFTER, "6 PM"),
        ("By 6 PM, residents must evacuate Zone A.", TemporalOperator.BY, "6 PM"),
        ("Until 6 PM, residents must evacuate Zone A.", TemporalOperator.UNTIL, "6 PM"),
    ],
)
def test_simple_preposed_temporal_operator_is_bound(text: str, operator: TemporalOperator, value: str) -> None:
    action = first_action(text)
    assert [(x.operator, x.time) for x in action.temporal_constraints] == [(operator, value)]
    assert not E.extract(text).unresolved_operational_text


def test_source_preposed_time_deletion_cannot_pass() -> None:
    assert verify(
        "At 6 PM, residents must evacuate Zone A.",
        "Residents must evacuate Zone A.",
    ).decision != Decision.PASS


def test_candidate_preposed_time_addition_cannot_pass() -> None:
    assert verify(
        "Residents must evacuate Zone A.",
        "At 6 PM, residents must evacuate Zone A.",
    ).decision != Decision.PASS


def test_preposed_operator_reversal_blocks() -> None:
    assert verify(
        "Before 6 PM, residents must evacuate Zone A.",
        "After 6 PM, residents must evacuate Zone A.",
    ).decision == Decision.BLOCK


@pytest.mark.parametrize(
    ("source", "candidate"),
    [
        ("At 6 PM, residents must evacuate Zone A.", "Residents must evacuate Zone A at 18:00."),
        ("At 6 p.m., residents must evacuate Zone A.", "Residents must evacuate Zone A at 18:00."),
        ("At noon, residents must evacuate Zone A.", "Residents must evacuate Zone A at 12 PM."),
    ],
)
def test_preposed_postposed_equivalent_normalization_passes(source: str, candidate: str) -> None:
    assert verify(source, candidate).decision == Decision.PASS


@pytest.mark.parametrize(
    "text",
    [
        "Residents must evacuate at 6 PM.",
        "Residents must evacuate starting at 6 PM.",
        "Residents must evacuate on Friday.",
        "Residents must evacuate before 6 PM.",
        "Residents must evacuate after 6 PM.",
        "Residents must evacuate by 6 PM.",
        "Residents must evacuate until 6 PM.",
    ],
)
def test_existing_post_action_temporal_support_remains_structured(text: str) -> None:
    action = first_action(text)
    assert action.temporal_constraints
    assert not E.extract(text).unresolved_operational_text


def test_ambiguous_prefix_shared_by_two_actions_is_unresolved_not_guessed() -> None:
    text = "At 6 PM, residents must evacuate Zone A and shelter indoors."
    contract = E.extract(text)
    assert contract.unresolved_operational_text
    assert all(not action.temporal_constraints for action in contract.required_actions)
    assert V.verify(contract, contract).decision == Decision.REVIEW


@pytest.mark.parametrize(
    "text",
    [
        "If water reaches the bridge at 6 PM, residents must evacuate Zone A.",
        "When sirens sound at 6 PM, residents must evacuate Zone A.",
        "If flooding begins after 6 PM, residents must evacuate Zone A.",
        "Residents must evacuate Zone A if sirens sound at 6 PM.",
    ],
)
def test_condition_internal_time_is_not_rebound_as_action_time(text: str) -> None:
    contract = E.extract(text)
    action = contract.required_actions[0]
    assert action.condition
    assert not action.temporal_constraints


def test_condition_internal_time_change_is_detected_through_condition_semantics() -> None:
    result = verify(
        "If water reaches the bridge at 6 PM, residents must evacuate Zone A.",
        "If water reaches the bridge at 8 PM, residents must evacuate Zone A.",
    )
    assert result.decision == Decision.BLOCK


def test_prefix_time_before_unrepresented_condition_fails_closed() -> None:
    text = "At 6 PM, if sirens sound, residents must evacuate Zone A."
    contract = E.extract(text)
    assert contract.unresolved_operational_text
    assert V.verify(contract, contract).decision == Decision.REVIEW


@pytest.mark.parametrize(
    "text",
    [
        "Alert issued at 6 PM. Residents must evacuate Zone A.",
        "Updated at 6 PM. Residents must evacuate Zone A.",
        "For information at 6 PM, call 311. Residents must evacuate Zone A.",
        "The briefing begins at 6 PM. Residents must evacuate Zone A.",
        "Weather conditions were observed at 6 PM. Residents must evacuate Zone A.",
    ],
)
def test_informational_time_is_never_blindly_attached_to_later_action(text: str) -> None:
    contract = E.extract(text)
    assert contract.required_actions
    assert not contract.required_actions[-1].temporal_constraints


@pytest.mark.parametrize(
    ("source", "candidate"),
    [
        ("At 6 PM, residents must evacuate Zone A.", "Residents must evacuate Zone A."),
        ("Residents must evacuate Zone A.", "At 6 PM, residents must evacuate Zone A."),
        ("At 6 PM, residents must evacuate Zone A.", "At 8 PM, residents must evacuate Zone A."),
        ("Before 6 PM, residents must evacuate Zone A.", "After 6 PM, residents must evacuate Zone A."),
    ],
)
def test_source_candidate_temporal_asymmetry_never_passes(source: str, candidate: str) -> None:
    assert verify(source, candidate).decision != Decision.PASS


@pytest.mark.parametrize(
    ("source", "candidate"),
    [
        ("Before 6 PM, residents must evacuate Zone A.", "After 6 PM, residents must evacuate Zone A."),
        ("By 6 PM, residents must evacuate Zone A.", "At 6 PM, residents must evacuate Zone A."),
        ("Until 6 PM, residents must evacuate Zone A.", "Before 6 PM, residents must evacuate Zone A."),
        ("Starting at 6 PM, residents must evacuate Zone A.", "Until 6 PM, residents must evacuate Zone A."),
        ("On Friday, residents must evacuate Zone A.", "On Saturday, residents must evacuate Zone A."),
    ],
)
def test_preposed_operator_differences_block(source: str, candidate: str) -> None:
    assert verify(source, candidate).decision == Decision.BLOCK


@pytest.mark.parametrize(
    "text",
    [
        "At 6 PM residents must evacuate Zone A.",
        "At 6 PM: residents must evacuate Zone A.",
    ],
)
def test_common_preposed_punctuation_variants_bind(text: str) -> None:
    action = first_action(text)
    assert [(x.operator, x.time) for x in action.temporal_constraints] == [(TemporalOperator.AT, "6 PM")]


def test_em_dash_preposed_time_is_normalized_and_bound() -> None:
    contract = E.extract("At 6 PM — residents must evacuate Zone A.")
    action = contract.required_actions[0]
    assert [(x.operator, x.time) for x in action.temporal_constraints] == [(TemporalOperator.AT, "6 PM")]
    assert V.verify(contract, contract).decision == Decision.PASS


MULTI_SOURCE = "At 6 PM, Zone A residents must evacuate. At 8 PM, Zone B residents must shelter indoors."
MULTI_SWAPPED = "At 8 PM, Zone A residents must evacuate. At 6 PM, Zone B residents must shelter indoors."
MULTI_POST_SOURCE = "Zone A residents must evacuate at 6 PM. Zone B residents must shelter indoors at 8 PM."
MULTI_POST_SWAPPED = "Zone A residents must evacuate at 8 PM. Zone B residents must shelter indoors at 6 PM."


def test_multi_instruction_prefix_times_bind_to_their_own_actions() -> None:
    contract = E.extract(MULTI_SOURCE)
    keys = [[(x.operator, x.time) for x in action.temporal_constraints] for action in contract.required_actions]
    assert keys == [[(TemporalOperator.AT, "6 PM")], [(TemporalOperator.AT, "8 PM")]]
    assert not contract.unresolved_operational_text


def test_same_global_times_with_wrong_prefix_attachment_block() -> None:
    assert verify(MULTI_SOURCE, MULTI_SWAPPED).decision == Decision.BLOCK


def test_same_global_times_with_wrong_postfix_attachment_block() -> None:
    assert verify(MULTI_POST_SOURCE, MULTI_POST_SWAPPED).decision == Decision.BLOCK


def test_semicolon_multiple_prefix_times_bind_separately() -> None:
    text = "At 6 PM, Zone A residents must evacuate; at 8 PM, Zone B residents must shelter indoors."
    contract = E.extract(text)
    keys = [[(x.operator, x.time) for x in action.temporal_constraints] for action in contract.required_actions]
    assert keys == [[(TemporalOperator.AT, "6 PM")], [(TemporalOperator.AT, "8 PM")]]


@pytest.mark.parametrize(
    "text",
    [
        "Tonight, residents must evacuate Zone A.",
        "Tomorrow, residents must evacuate Zone A.",
        "This evening, residents must evacuate Zone A.",
        "Immediately, residents must evacuate Zone A.",
    ],
)
def test_relative_time_is_represented_or_fails_closed(text: str) -> None:
    contract = E.extract(text)
    if not contract.required_actions[0].temporal_constraints:
        represented_as_urgency = contract.urgency.value != "Unknown"
        assert contract.unresolved_operational_text or represented_as_urgency
        if contract.unresolved_operational_text:
            assert V.verify(contract, contract).decision == Decision.REVIEW


@pytest.mark.parametrize(
    "text",
    [
        "500 residents must evacuate Zone A.",
        "Zone 6 residents must evacuate.",
        "Route 6 users must evacuate.",
        "Alert 6 requires residents to evacuate.",
    ],
)
def test_ordinary_numbers_are_not_mistaken_for_action_times(text: str) -> None:
    contract = E.extract(text)
    for action in contract.required_actions:
        assert not action.temporal_constraints


def test_gate2m_uncertainty_and_preposed_time_compose_fail_closed() -> None:
    source = "At 6 PM, residents must evacuate Zone A. निवासी घर में रहें।"
    assert verify(source, "Residents must evacuate Zone A. निवासी घर में रहें।").decision != Decision.PASS
    assert verify(source, "At 6 PM, residents must evacuate Zone A.").decision != Decision.PASS
    assert verify(source, "Residents must evacuate Zone A.").decision != Decision.PASS


FRESH_TEMPORAL_PAIRS = [
    ("At 5 AM residents must evacuate Zone B.", "At 7 AM residents must evacuate Zone B."),
    ("At 18:00: visitors must evacuate Zone C.", "At 20:00: visitors must evacuate Zone C."),
    ("At 6 PM, drivers must avoid roads.", "At 8 PM, drivers must avoid roads."),
    ("Starting at 7 AM residents must shelter indoors.", "Starting at 9 AM residents must shelter indoors."),
    ("From noon, residents must stay indoors.", "From 3 PM, residents must stay indoors."),
    ("On Monday, visitors must evacuate Zone D.", "On Tuesday, visitors must evacuate Zone D."),
    ("On 10 October, residents must evacuate Zone E.", "On 11 October, residents must evacuate Zone E."),
    ("Before 5 PM, residents must boil water.", "After 5 PM, residents must boil water."),
    ("After 5 PM, residents must avoid roads.", "Before 5 PM, residents must avoid roads."),
    ("By 7 PM, residents must evacuate Zone F.", "By 9 PM, residents must evacuate Zone F."),
    ("Until 7 PM, residents must shelter indoors.", "Until 9 PM, residents must shelter indoors."),
    ("At 6 PM — residents must evacuate Zone A.", "At 8 PM — residents must evacuate Zone A."),
    ("At 6 PM: residents must evacuate Zone A.", "At 8 PM: residents must evacuate Zone A."),
    ("At 6 PM, Zone A residents must evacuate. At 8 PM, Zone B residents must shelter indoors.", "At 7 PM, Zone A residents must evacuate. At 8 PM, Zone B residents must shelter indoors."),
    ("At 6 PM, Zone A residents must evacuate; at 8 PM, Zone B residents must shelter indoors.", "At 6 PM, Zone A residents must evacuate; at 9 PM, Zone B residents must shelter indoors."),
    ("Zone A residents must evacuate at 6 PM. At 8 PM, Zone B residents must shelter indoors.", "Zone A residents must evacuate at 7 PM. At 8 PM, Zone B residents must shelter indoors."),
    ("At 6 AM, students must evacuate Zone 3.", "At 9 AM, students must evacuate Zone 3."),
    ("Starting Friday, residents must evacuate Zone A.", "Starting Saturday, residents must evacuate Zone A."),
    ("No later than 6 PM, residents must evacuate Zone A.", "No later than 8 PM, residents must evacuate Zone A."),
    ("Prior to 6 PM, residents must evacuate Zone A.", "After 6 PM, residents must evacuate Zone A."),
]


@pytest.mark.parametrize(("source", "candidate"), FRESH_TEMPORAL_PAIRS)
def test_fresh_same_root_temporal_search_has_zero_false_passes(source: str, candidate: str) -> None:
    assert verify(source, candidate).decision != Decision.PASS


EQUIVALENT_TEMPORAL_PAIRS = [
    ("At 6 PM, residents must evacuate Zone A.", "Residents must evacuate Zone A at 18:00."),
    ("At 6 p.m., residents must evacuate Zone A.", "Residents must evacuate Zone A at 18:00."),
    ("At noon, residents must evacuate Zone A.", "Residents must evacuate Zone A at 12 PM."),
    ("On Friday, residents must evacuate Zone A.", "Residents must evacuate Zone A on Friday."),
    ("On 25 September, residents must evacuate Zone A.", "Residents must evacuate Zone A on 25 September."),
    ("Starting at 6 PM, residents must evacuate Zone A.", "Residents must evacuate Zone A starting at 18:00."),
    ("From 6 PM, residents must evacuate Zone A.", "Residents must evacuate Zone A starting at 18:00."),
    ("Before 6 PM, residents must evacuate Zone A.", "Residents must evacuate Zone A prior to 6 PM."),
    ("After 6 PM, residents must evacuate Zone A.", "Residents must evacuate Zone A after 18:00."),
    ("By 6 PM, residents must evacuate Zone A.", "Residents must evacuate Zone A no later than 18:00."),
    ("Until 6 PM, residents must shelter indoors.", "Residents must shelter indoors until 18:00."),
    ("At 6 PM residents must evacuate Zone A.", "At 6 PM, residents must evacuate Zone A."),
    ("At 6 PM: residents must evacuate Zone A.", "At 6 PM, residents must evacuate Zone A."),
    ("Residents must evacuate Zone A.", "Residents must evacuate Zone A."),
    ("At 6 AM, visitors must evacuate Zone C.", "Visitors must evacuate Zone C at 06:00."),
    ("On Monday, residents must stay indoors.", "Residents must shelter indoors on Monday."),
    ("Starting at noon, residents must stay indoors.", "Residents must shelter indoors starting at 12 PM."),
    ("Before noon, residents must avoid roads.", "Residents must avoid roads before 12 PM."),
    ("After noon, residents must boil water.", "Residents must boil water after 12 PM."),
    ("By noon, residents must evacuate Zone A.", "Residents must evacuate Zone A by 12 PM."),
]


@pytest.mark.parametrize(("source", "candidate"), EQUIVALENT_TEMPORAL_PAIRS)
def test_supported_equivalent_temporal_controls_remain_pass(source: str, candidate: str) -> None:
    assert verify(source, candidate).decision == Decision.PASS
