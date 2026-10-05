import pytest

from signallock.benchmark.runner import validate_provenance
from signallock.contracts.extractor import HeuristicExtractor
from signallock.contracts.schema import ActionType


TEXT = (
    "Residents in the eastern river district must shelter indoors until 6 PM. "
    "Do not enter the eastern underpass. "
    "Avoid roads with more than 30 cm of water, except emergency personnel."
)


def test_extract_core_contract():
    contract = HeuristicExtractor().extract(TEXT)
    assert contract.audience[0].lower() == "residents"
    assert "eastern river district" in [x.lower() for x in contract.affected_areas]
    assert any(a.type == ActionType.SHELTER for a in contract.required_actions)
    assert any(a.verb.lower() == "enter" for a in contract.prohibited_actions)
    assert contract.required_actions[0].deadline == "6 PM"
    assert contract.quantities[0].value == 30
    assert contract.exceptions


def test_evidence_spans_are_exact():
    contract = HeuristicExtractor().extract(TEXT)
    assert validate_provenance(TEXT, contract) == []


def test_empty_rejected():
    with pytest.raises(ValueError):
        HeuristicExtractor().extract("   ")


def test_non_english_demo_rejected():
    with pytest.raises(ValueError):
        HeuristicExtractor().extract("चेतावनी", language="hi")
