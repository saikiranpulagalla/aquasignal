import pytest

from aquasignal.domain.freshwater import FreshwaterExtractor, assess_source_readiness
from aquasignal.integrity.verifier import AquaVerificationEngine


ext = FreshwaterExtractor()
verifier = AquaVerificationEngine()


def decision(source: str, candidate: str) -> str:
    s = ext.extract(source, source_id="source")
    c = ext.extract(candidate, source_id="candidate")
    assert assess_source_readiness(s).ready, s.unresolved_operational_text
    return verifier.verify(s, c).decision.value


@pytest.mark.parametrize(
    "text",
    [
        "Do not swim or kayak in Stream A until 18:00.",
        "Avoid direct contact with Stream A from 18:00 to 20:00.",
        "Avoid direct contact with Stream A until Monday.",
        "If testing remains elevated, avoid direct contact with Stream A until 18:00.",
        "Except emergency crews, visitors must avoid contact with Stream A until 18:00.",
        "Keep children and dogs away from Stream A until 18:00.",
        "Boil the water for at least one minute before drinking.",
        "Do not swim in Stream A until 18:00. Wear gloves.",
        "Avoid direct contact with Stream A until further notice.",
        "Avoid direct contact with Stream A for the next 2 hours.",
        "Avoid direct contact with Stream A until 18:00 UTC.",
        "Avoid direct contact with the north bank of Stream A until 18:00.",
        "Visitors and pregnant people must avoid contact with Stream A until 18:00.",
    ],
)
def test_partial_or_unsupported_authority_fails_source_readiness(text):
    contract = ext.extract(text)
    assert contract.unresolved_operational_text, text
    assert not assess_source_readiness(contract).ready


@pytest.mark.parametrize(
    "source,candidate",
    [
        (
            "Visitors must avoid contact with Stream A until 18:00.",
            "Visitors may avoid contact with Stream A until 18:00.",
        ),
        (
            "Visitors must avoid contact with Stream A until 18:00.",
            "Visitors can avoid contact with Stream A until 18:00.",
        ),
        (
            "Visitors must avoid contact with Stream A until 18:00.",
            "Visitors must not avoid contact with Stream A until 18:00.",
        ),
        (
            "Do not swim in Stream A until 18:00.",
            "Do not swim in Stream A until 18:00. Wear gloves.",
        ),
        (
            "Do not swim in Stream A until 18:00.",
            "Do not swim in Stream A until 18:00. Call 911.",
        ),
        (
            "Keep children and pets away from Stream A until 18:00.",
            "Keep children and dogs away from Stream A until 18:00.",
        ),
        (
            "Avoid direct contact with River Great Ouse until 18:00.",
            "Avoid direct contact with River Great until 18:00.",
        ),
    ],
)
def test_unsafe_boundary_candidate_never_passes(source, candidate):
    assert decision(source, candidate) != "PASS"


@pytest.mark.parametrize(
    "source,candidate",
    [
        (
            "Boil the water for at least 3 minutes before drinking.",
            "Boil the water for at least 3 mins before drinking.",
        ),
        (
            "Boil the water for at least 1 hour before drinking.",
            "Boil the water for at least 60 minutes before drinking.",
        ),
        (
            "Boil the water for at least 1 minute before drinking.",
            "Boil the water for at least 60 seconds before drinking.",
        ),
    ],
)
def test_supported_duration_equivalences_pass(source, candidate):
    assert decision(source, candidate) == "PASS"


def test_multiword_waterbody_identifier_is_preserved():
    contract = ext.extract("Avoid direct contact with River Great Ouse until 18:00.")
    assert assess_source_readiness(contract).ready
    assert "river great ouse" in {x.casefold() for x in contract.affected_areas}


def test_unrecognized_candidate_sentence_forces_review():
    source = "Do not swim in Stream A until 18:00."
    candidate = "Do not swim in Stream A until 18:00. Stay home."
    assert decision(source, candidate) == "REVIEW"


def test_directional_words_inside_proper_names_remain_supported():
    for text in (
        "Avoid direct contact downstream of Bridge North until 17:30.",
        "Avoid direct contact with River North until 17:30.",
    ):
        contract = ext.extract(text)
        assert assess_source_readiness(contract).ready, (text, contract.unresolved_operational_text)


@pytest.mark.parametrize("time", ["99:99", "24:00", "13:75", "0 PM", "13 PM"])
def test_invalid_clock_values_fail_source_readiness(time):
    contract = ext.extract(f"Avoid direct contact with Stream A until {time}.")
    assert not assess_source_readiness(contract).ready


def test_typographic_apostrophe_in_dont_is_clean_equivalence():
    result = decision(
        "Do not swim in Stream A until 18:00.",
        "Don’t swim in Stream A until 18:00.",
    )
    assert result == "PASS"


def test_typographic_apostrophe_in_named_place_is_clean_equivalence():
    result = decision(
        "Avoid direct contact with River O'Neil until 18:00.",
        "Avoid direct contact with River O’Neil until 18:00.",
    )
    assert result == "PASS"


def test_typographic_dash_in_named_place_is_clean_equivalence():
    result = decision(
        "Do not swim in Stream Alpha-2 until 18:00.",
        "Do not swim in Stream Alpha–2 until 18:00.",
    )
    assert result == "PASS"


def test_attached_ampm_is_clean_equivalence():
    result = decision(
        "Do not swim in Stream A until 18:00.",
        "Do not swim in Stream A until 6pm.",
    )
    assert result == "PASS"


def test_terminal_semicolon_does_not_change_meaning():
    result = decision(
        "Do not swim in Stream A until 18:00.",
        "Do not swim in Stream A until 18:00;",
    )
    assert result == "PASS"


def test_unicode_confusable_keyword_does_not_silently_pass():
    # Greek omicron in "nοt" must not normalize into an English keyword.
    result = decision(
        "Do not swim in Stream A until 18:00.",
        "Do nοt swim in Stream A until 18:00.",
    )
    assert result != "PASS"


def test_exact_duplicate_supported_directive_does_not_create_new_operational_meaning():
    result = decision(
        "Do not swim in Stream A until 18:00.",
        "Do not swim in Stream A until 18:00. Do not swim in Stream A until 18:00.",
    )
    assert result == "PASS"


@pytest.mark.parametrize(
    "candidate",
    [
        "Avoid contact with water in Stream A until 18:00.",
        "Avoid contact with the water in Stream A until 18:00.",
        "Avoid direct contact with stream water in Stream A until 18:00.",
    ],
)
def test_explicit_water_medium_in_named_site_is_clean_contact_equivalence(candidate):
    assert decision("Avoid direct contact with Stream A until 18:00.", candidate) == "PASS"


@pytest.mark.parametrize(
    "source,candidate",
    [
        (
            "Do not swim in Stream A until 18:00.",
            "Swimming is prohibited in Stream A until 18:00.",
        ),
        (
            "Avoid direct contact with Stream A until 18:00.",
            "Please avoid touching the water in Stream A until 18:00.",
        ),
        (
            "Keep children and pets away from Stream A until 18:00.",
            "Children and pets should stay away from Stream A until 18:00.",
        ),
    ],
)
def test_fully_unsupported_candidate_language_is_review_not_false_block(source, candidate):
    assert decision(source, candidate) == "REVIEW"


def test_unresolved_candidate_does_not_mask_independently_parsed_contradiction():
    assert decision(
        "Do not swim in Stream A until 18:00.",
        "Swim in Stream A until 18:00. Stay home.",
    ) == "BLOCK"


def test_unicode_freshwater_place_names_are_supported_without_broadening_operational_grammar():
    for text in (
        "Avoid direct contact with River São Pedro until 18:00.",
        "Avoid direct contact with River München until 18:00.",
        "Avoid direct contact downstream of Ponte São João until 18:00.",
    ):
        contract = ext.extract(text)
        assert assess_source_readiness(contract).ready, (text, contract.unresolved_operational_text)


def test_unicode_place_nfc_nfd_forms_are_clean_equivalent():
    source = "Avoid direct contact with River São Pedro until 18:00."
    candidate = "Avoid direct contact with River Sa\u0303o Pedro until 18:00."
    assert decision(source, candidate) == "PASS"


@pytest.mark.parametrize(
    "text",
    [
        "Do not swim in Stream A until 18:00. Should not swim in Stream A until 18:00.",
        "Do not swim in Stream A until 18:00. Do not swim in Stream A until 19:00.",
        "Boil the water for at least 1 minute before drinking. Boil the water for at least 2 minutes before drinking.",
    ],
)
def test_conflicting_duplicate_authoritative_directives_fail_source_readiness(text):
    contract = ext.extract(text)
    readiness = assess_source_readiness(contract)
    assert not readiness.ready
    assert any("conflicting" in reason.casefold() for reason in readiness.reasons)


def test_permissive_may_contact_rewrite_is_structured_and_blocks_strong_source():
    assert decision(
        "Visitors must avoid contact with Stream A until 18:00.",
        "Visitors may avoid contact with Stream A until 18:00.",
    ) == "BLOCK"
    candidate = ext.extract("Visitors may avoid contact with Stream A until 18:00.")
    assert candidate.prohibited_actions
    assert candidate.unresolved_operational_text


def test_only_field_staff_sampling_is_supported_and_exclusivity_loss_blocks():
    source = "Only field staff may collect samples from Site A."
    source_contract = ext.extract(source)
    assert assess_source_readiness(source_contract).ready
    assert decision(source, "Field staff may collect samples from Site A.") == "BLOCK"

@pytest.mark.parametrize(
    "text",
    [
        "Do not swim in Stream A and wear gloves until 18:00.",
        "Do not swim in Stream A or call 911 until 18:00.",
        "Keep children and pets away from Stream A and call 911 until 18:00.",
        "Avoid direct contact with Stream A and wash hands until 18:00.",
    ],
)
def test_named_place_scope_cannot_swallow_extra_operational_clause(text):
    contract = ext.extract(text)
    assert not assess_source_readiness(contract).ready
    assert contract.unresolved_operational_text


def test_audience_statement_without_modal_is_not_treated_as_authoritative_imperative():
    contract = ext.extract("Visitors avoid contact with Stream A until 18:00.")
    assert not assess_source_readiness(contract).ready


@pytest.mark.parametrize(
    "source,candidate",
    [
        (
            "Visitors must avoid contact with Stream A until 6 PM.",
            "Visitors should avoid contact with Stream A until 18:00.",
        ),
        (
            "Do not swim in Stream A until 6 PM.",
            "Should not swim in Stream A until 18:00.",
        ),
    ],
)
def test_force_weakening_blocks_even_when_clock_format_changes(source, candidate):
    assert decision(source, candidate) == "BLOCK"


@pytest.mark.parametrize(
    "candidate",
    [
        "Visitors do not avoid contact with Stream A until 18:00.",
        "Visitors don't avoid contact with Stream A until 18:00.",
        "Visitors never avoid contact with Stream A until 18:00.",
        "Visitors should not avoid contact with Stream A until 18:00.",
        "Visitors must not avoid contact with Stream A until 18:00.",
    ],
)
def test_negated_avoid_contact_is_decisive_polarity_reversal(candidate):
    assert decision(
        "Visitors must avoid contact with Stream A until 18:00.",
        candidate,
    ) == "BLOCK"


@pytest.mark.parametrize("duration", ["0 minutes", "0.0 hours", "0 seconds"])
def test_nonpositive_boil_duration_fails_source_readiness(duration):
    contract = ext.extract(f"Boil the water for {duration} before drinking.")
    assert not assess_source_readiness(contract).ready

@pytest.mark.parametrize(
    "text",
    [
        "Do not swim in Stream A then wear gloves until 18:00.",
        "Do not swim in Stream A plus call 911 until 18:00.",
        "Avoid direct contact with Stream A also wash hands until 18:00.",
        "Avoid direct contact with Stream A because contamination was reported until 18:00.",
        "Keep children away from Stream A when testing is elevated until 18:00.",
    ],
)
def test_named_scope_rejects_clause_connectors_and_embedded_operational_phrases(text):
    contract = ext.extract(text)
    assert not assess_source_readiness(contract).ready
    assert contract.unresolved_operational_text


@pytest.mark.parametrize(
    "source,candidate",
    [
        ("Do not swim in Stream A until 18:00.", "Visitors may swim in Stream A until 18:00."),
        ("Do not fish in Stream A until 18:00.", "Residents can fish in Stream A until 18:00."),
        ("Avoid direct contact with Stream A until 18:00.", "Visitors may touch the water in Stream A until 18:00."),
        ("Avoid direct contact with Stream A until 18:00.", "Residents should contact the water in Stream A until 18:00."),
    ],
)
def test_explicit_positive_permission_or_instruction_against_prohibition_blocks(source, candidate):
    assert decision(source, candidate) == "BLOCK"

@pytest.mark.parametrize(
    "source,candidate",
    [
        ("Do not swim in Stream A until 18:00.", "Do not swim in Stream A, until 18:00."),
        ("Avoid direct contact with Stream A until 6 PM.", "Avoid direct contact with Stream A, until 18:00."),
        ("Keep children and pets away from Stream A until 18:00.", "Keep children and pets away from Stream A, until 6 PM."),
    ],
)
def test_comma_before_supported_temporal_suffix_is_clean_equivalence(source, candidate):
    assert decision(source, candidate) == "PASS"
