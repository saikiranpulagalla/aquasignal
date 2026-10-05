import pytest

from aquasignal.domain.freshwater import FreshwaterExtractor, assess_source_readiness
from aquasignal.integrity.verifier import AquaVerificationEngine


def verify(source: str, candidate: str):
    ext = FreshwaterExtractor()
    s = ext.extract(source, source_id="source")
    c = ext.extract(candidate, source_id="candidate")
    return s, c, AquaVerificationEngine().verify(s, c)


def test_source_readiness_rejects_unsupported_authority():
    ext = FreshwaterExtractor()
    contract = ext.extract("Authorities are evaluating conditions and will issue more information later.")
    readiness = assess_source_readiness(contract)
    assert not readiness.ready


def test_time_reversal_blocks():
    source = "Visitors must avoid contact with Stream A after 18:00."
    candidate = "Visitors must avoid contact with Stream A before 18:00."
    s, _, result = verify(source, candidate)
    assert assess_source_readiness(s).ready
    assert result.decision.value == "BLOCK"


def test_clock_equivalence_passes():
    source = "Visitors must avoid contact with Stream A until 6 PM."
    candidate = "Visitors must avoid contact with Stream A until 18:00."
    _, _, result = verify(source, candidate)
    assert result.decision.value == "PASS"


def test_audience_omission_blocks():
    source = "Keep children and pets away from Stream A until 18:00."
    candidate = "Keep children away from Stream A until 18:00."
    _, _, result = verify(source, candidate)
    assert result.decision.value == "BLOCK"
    assert any(s.field in {"required_action", "audience"} and s.status == "FAIL" for s in result.signals)


def test_downstream_upstream_blocks_with_aqua_policy():
    source = "Avoid direct contact with stream water downstream of Bridge A until 18:00."
    candidate = "Avoid direct contact with stream water upstream of Bridge A until 18:00."
    _, _, result = verify(source, candidate)
    assert result.decision.value == "BLOCK"
    assert any(s.field == "place_relation" and s.status == "FAIL" for s in result.signals)


def test_swim_or_fish_omission_blocks():
    source = "Do not swim or fish in Stream A until 18:00."
    candidate = "Do not swim in Stream A until 18:00."
    _, _, result = verify(source, candidate)
    assert result.decision.value == "BLOCK"


def test_hallucinated_boiling_advice_blocks():
    source = "Avoid direct contact with Stream A until 18:00."
    candidate = "Avoid direct contact with Stream A until 18:00. Boil the water for at least 1 minute before drinking."
    _, _, result = verify(source, candidate)
    assert result.decision.value == "BLOCK"
    assert any(s.field.startswith("candidate_only_") and s.status == "FAIL" for s in result.signals)


def test_boil_duration_is_not_water_depth():
    ext = FreshwaterExtractor()
    contract = ext.extract("Boil the water for at least 1 minute before drinking.")
    assert not contract.unresolved_operational_text
    assert contract.quantities
    assert contract.quantities[0].meaning == "boil duration"
    assert contract.quantities[0].value == 1


def test_relative_time_fails_closed():
    ext = FreshwaterExtractor()
    contract = ext.extract("Avoid direct contact with Stream A this afternoon.")
    assert contract.unresolved_operational_text
    assert not assess_source_readiness(contract).ready


def test_stream_water_is_not_parsed_as_named_stream_identifier():
    ext = FreshwaterExtractor()
    contract = ext.extract("Avoid direct contact with stream water downstream of Bridge A until 18:00.")
    assert "stream water" not in {x.casefold() for x in contract.affected_areas}
    assert "downstream of bridge a" in {x.casefold() for x in contract.affected_areas}


def test_named_site_identifier_change_blocks_even_for_single_letter_ids():
    _, _, result = verify(
        "Avoid direct contact with Stream A until 18:00.",
        "Avoid direct contact with Stream B until 18:00.",
    )
    assert result.decision.value == "BLOCK"
    assert any(s.field == "place_identifier" and s.status == "FAIL" for s in result.signals)


def test_relative_landmark_change_blocks_and_preserves_single_letter_id():
    _, _, result = verify(
        "Avoid direct contact downstream of Bridge A until 18:00.",
        "Avoid direct contact downstream of Bridge B until 18:00.",
    )
    assert result.decision.value == "BLOCK"
    assert any(s.field == "place_relation" and s.status == "FAIL" for s in result.signals)


def test_reverse_coordinated_prohibition_addition_blocks():
    source = "Do not fish in River C until 20:00."
    candidate = "Do not fish or swim in River C until 20:00."
    _, _, result = verify(source, candidate)
    assert result.decision.value == "BLOCK"
    assert any(s.field.startswith("candidate_only_") and s.status == "FAIL" for s in result.signals)


def test_must_not_prohibition_is_supported():
    ext = FreshwaterExtractor()
    contract = ext.extract("Visitors must not swim in Stream A until 18:00.")
    assert not contract.unresolved_operational_text
    assert any(a.verb == "swim" for a in contract.prohibited_actions)


def test_strong_avoidance_weakened_to_should_blocks():
    _, _, result = verify(
        "Visitors must avoid contact with Stream A until 18:00.",
        "Visitors should avoid contact with Stream A until 18:00.",
    )
    assert result.decision.value == "BLOCK"


def test_strong_prohibition_weakened_to_should_not_blocks():
    _, _, result = verify(
        "Do not swim in Stream A until 18:00.",
        "Should not swim in Stream A until 18:00.",
    )
    assert result.decision.value == "BLOCK"


def test_permission_reversal_never_receives_automatic_pass():
    _, _, result = verify(
        "Do not wade in Stream A until 18:00.",
        "You may wade in Stream A until 18:00.",
    )
    # V17-sealed semantics intentionally handle this unsupported positive phrasing
    # conservatively as REVIEW. This regression protects the hard safety boundary
    # without widening the profile or requiring a new holdout.
    assert result.decision.value != "PASS"


def test_equivalent_strong_contact_prohibitions_still_pass():
    _, _, result = verify(
        "Avoid direct contact with Stream A until 18:00.",
        "Do not touch water in Stream A until 18:00.",
    )
    assert result.decision.value == "PASS"


def test_negative_and_coordination_fails_closed():
    ext = FreshwaterExtractor()
    contract = ext.extract("Do not swim and fish in Stream A until 18:00.")
    assert contract.unresolved_operational_text
    assert not assess_source_readiness(contract).ready


@pytest.mark.parametrize("verb", ["enter", "swim", "wade", "fish", "drink"])
def test_direct_prohibition_family_identity_and_time_loss(verb):
    source = f"Do not {verb} in Stream A until 18:00."
    _, _, same = verify(source, source)
    _, _, time_lost = verify(source, f"Do not {verb} in Stream A.")
    assert same.decision.value == "PASS"
    assert time_lost.decision.value == "BLOCK"


@pytest.mark.parametrize("verb", ["enter", "swim", "wade", "fish", "drink"])
def test_direct_prohibition_force_weakening_blocks_across_supported_verbs(verb):
    _, _, result = verify(
        f"Do not {verb} in Stream A until 18:00.",
        f"Should not {verb} in Stream A until 18:00.",
    )
    assert result.decision.value == "BLOCK"


@pytest.mark.parametrize("first,second", [("swim", "fish"), ("fish", "swim"), ("wade", "fish"), ("drink", "swim")])
def test_supported_or_coordination_is_order_symmetric(first, second):
    source = f"Do not {first} or {second} in Stream A until 18:00."
    _, _, result = verify(source, source)
    assert result.decision.value == "PASS"
