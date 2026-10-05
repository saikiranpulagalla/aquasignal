from signallock.contracts.extractor import HeuristicExtractor
from signallock.contracts.schema import Action, ActionType, SafetyContract
from signallock.verification.engine import VerificationEngine

V = VerificationEngine()


def test_typed_action_with_contradictory_verb_blocks():
    source = SafetyContract(required_actions=[Action(type=ActionType.SHELTER, verb="shelter", destination="indoors")])
    candidate = SafetyContract(required_actions=[Action(type=ActionType.SHELTER, verb="evacuate", destination="indoors")])
    assert V.verify(source, candidate).decision.value == "BLOCK"


def test_small_numeric_location_identifier_change_blocks():
    source = SafetyContract(affected_areas=["Evacuation Zone 104"])
    candidate = SafetyContract(affected_areas=["Evacuation Zone 105"])
    assert V.verify(source, candidate).decision.value == "BLOCK"


def test_urgency_phrase_reversal_blocks():
    e = HeuristicExtractor()
    source = e.extract("Evacuate immediately.")
    candidate = e.extract("Evacuate tomorrow.")
    assert V.verify(source, candidate).decision.value == "BLOCK"


def test_close_but_unverified_text_becomes_review_not_pass():
    source = SafetyContract(affected_areas=["Central Riverside District"])
    candidate = SafetyContract(affected_areas=["Central River District"])
    assert V.verify(source, candidate).decision.value != "PASS"


def test_authoritative_internal_contradiction_reviews_even_when_candidate_matches():
    e = HeuristicExtractor()
    text = "Shelter indoors. Do not shelter indoors."
    contract = e.extract(text)
    result = V.verify(contract, contract)
    assert result.decision.value == "REVIEW"
    assert any(s.field == "source_internal_contradiction" for s in result.signals)


def test_unrelated_required_and_prohibited_actions_are_not_false_conflicts():
    source = SafetyContract(
        required_actions=[Action(type=ActionType.SHELTER, verb="shelter", destination="indoors")],
        prohibited_actions=[Action(type=ActionType.AVOID, verb="enter", object="underpass", negated=True)],
    )
    assert V.verify(source, source).decision.value == "PASS"
