from datetime import datetime, timezone

import pytest

from signallock.contracts.extractor import HeuristicExtractor
from signallock.contracts.schema import (
    Action,
    ActionType,
    Certainty,
    ExceptionRule,
    Hazard,
    Quantity,
    SafetyContract,
    Severity,
    Urgency,
)
from signallock.transforms.demo import DemoTransformer
from signallock.verification.engine import VerificationEngine

E = HeuristicExtractor()
V = VerificationEngine()
BASE = (
    "Residents in the eastern river district must shelter indoors until 6 PM. "
    "Do not enter the eastern underpass. Avoid roads with more than 30 cm of water, except emergency personnel."
)


def verify_text(source: str, candidate: str):
    return V.verify(E.extract(source), E.extract(candidate))


@pytest.mark.parametrize(
    "suffix",
    [
        " Evacuate immediately.",
        " Do not shelter indoors.",
        " Avoid water deeper than 3 cm.",
        " Residents in the western river district must also shelter indoors.",
        " Visitors should follow this alert too.",
    ],
)
def test_candidate_only_operational_facts_never_pass(suffix):
    assert verify_text(BASE, BASE + suffix).decision.value != "PASS"


@pytest.mark.parametrize(
    "source,candidate",
    [
        ("Move to higher ground immediately.", "Move to lower ground immediately."),
        ("Boil tap water for 3 minutes before drinking.", "Drink tap water without boiling."),
        ("Turn off the gas supply.", "Turn on the gas supply."),
        ("Take shelter on the second floor.", "Take shelter in the basement."),
        ("No evacuation is currently required.", "Evacuation is required immediately."),
        ("Stay away from windows.", "Stand near windows."),
    ],
)
def test_common_action_reversals_never_pass(source, candidate):
    assert verify_text(source, candidate).decision.value != "PASS"


def test_empty_contracts_review_not_pass():
    result = V.verify(SafetyContract(), SafetyContract())
    assert result.decision.value == "REVIEW"
    assert any(s.status == "UNKNOWN" for s in result.signals)


def test_scope_negation_is_not_substring_equivalence():
    assert verify_text(BASE, BASE.replace("Residents", "Non-residents", 1)).decision.value != "PASS"
    assert verify_text(BASE, BASE.replace("except emergency personnel", "except non-emergency personnel")).decision.value != "PASS"


def test_action_antonym_substring_does_not_match():
    source = SafetyContract(required_actions=[Action(type=ActionType.OTHER, verb="disconnect", object="gas supply")])
    candidate = SafetyContract(required_actions=[Action(type=ActionType.OTHER, verb="connect", object="gas supply")])
    assert V.verify(source, candidate).decision.value == "BLOCK"


@pytest.mark.parametrize(
    "source,candidate",
    [
        (
            SafetyContract(required_actions=[Action(type=ActionType.EVACUATE, verb="evacuate", condition="only if officials order")]),
            SafetyContract(required_actions=[Action(type=ActionType.EVACUATE, verb="evacuate")]),
        ),
        (
            SafetyContract(required_actions=[Action(type=ActionType.EVACUATE, verb="evacuate")]),
            SafetyContract(required_actions=[Action(type=ActionType.EVACUATE, verb="evacuate", destination="unsafe tunnel")]),
        ),
        (
            SafetyContract(required_actions=[Action(type=ActionType.EVACUATE, verb="evacuate")]),
            SafetyContract(required_actions=[Action(type=ActionType.EVACUATE, verb="evacuate", deadline="8 PM")]),
        ),
    ],
)
def test_action_semantics_are_symmetric(source, candidate):
    assert V.verify(source, candidate).decision.value == "BLOCK"


@pytest.mark.parametrize(
    "source,candidate",
    [
        (SafetyContract(hazard=Hazard(type="flood")), SafetyContract(hazard=Hazard(type="wildfire"))),
        (SafetyContract(severity=Severity.EXTREME), SafetyContract(severity=Severity.MINOR)),
        (SafetyContract(certainty=Certainty.OBSERVED), SafetyContract(certainty=Certainty.UNLIKELY)),
        (SafetyContract(urgency=Urgency.IMMEDIATE), SafetyContract(urgency=Urgency.FUTURE)),
        (
            SafetyContract(effective_at=datetime(2026, 9, 10, tzinfo=timezone.utc), expires_at=datetime(2026, 9, 10, 18, tzinfo=timezone.utc)),
            SafetyContract(effective_at=datetime(2026, 9, 10, tzinfo=timezone.utc), expires_at=datetime(2026, 9, 10, 20, tzinfo=timezone.utc)),
        ),
    ],
)
def test_previously_ignored_fields_do_not_pass_when_changed(source, candidate):
    assert V.verify(source, candidate).decision.value != "PASS"


def test_quantity_meaning_and_extra_quantity_are_checked():
    source = SafetyContract(quantities=[Quantity(value=30, unit="cm", meaning="water depth")])
    changed_meaning = SafetyContract(quantities=[Quantity(value=30, unit="cm", meaning="safe clearance")])
    extra = SafetyContract(quantities=[Quantity(value=30, unit="cm", meaning="water depth"), Quantity(value=3, unit="cm", meaning="water depth")])
    assert V.verify(source, changed_meaning).decision.value == "BLOCK"
    assert V.verify(source, extra).decision.value == "BLOCK"


def test_builtin_simplifier_remains_usable():
    transformed = DemoTransformer().transform(BASE, mode="simplify")
    assert verify_text(BASE, transformed).decision.value == "PASS"


@pytest.mark.parametrize(
    "candidate",
    [
        BASE.replace("eastern river district", "east river district"),
        BASE.replace("Do not enter the eastern underpass", "Keep out of the eastern underpass"),
        BASE.replace("shelter indoors", "remain inside"),
        BASE.replace("except emergency personnel", "except emergency staff"),
        BASE.replace("30 cm", "0.3 m"),
        BASE.replace("6 PM", "18:00"),
    ],
)
def test_safe_semantic_rewrites_do_not_block(candidate):
    assert verify_text(BASE, candidate).decision.value != "BLOCK"


def test_cross_language_free_text_does_not_false_block_when_typed_semantics_match():
    source = SafetyContract(
        language="en",
        audience=["residents"],
        affected_areas=["Eastern River District"],
        required_actions=[Action(type=ActionType.SHELTER, verb="shelter", destination="indoors")],
    )
    hindi = SafetyContract(
        language="hi",
        audience=["निवासी"],
        affected_areas=["पूर्वी नदी जिला"],
        required_actions=[Action(type=ActionType.SHELTER, verb="शरण लें", destination="घर के अंदर")],
    )
    assert V.verify(source, hindi).decision.value in {"PASS", "REVIEW"}
