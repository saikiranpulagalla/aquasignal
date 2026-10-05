from signallock.contracts.extractor import HeuristicExtractor
from signallock.verification.engine import VerificationEngine


def test_quantity_relation_flip_blocks_even_when_value_is_identical():
    e = HeuristicExtractor()
    v = VerificationEngine()
    source = e.extract("Avoid roads with more than 30 cm of water.")
    candidate = e.extract("Avoid roads with less than 30 cm of water.")
    result = v.verify(source, candidate)
    assert result.decision.value == "BLOCK"
    assert any(s.field == "quantity" and s.status == "FAIL" for s in result.signals)


def test_equivalent_unit_preserves_relation():
    e = HeuristicExtractor()
    v = VerificationEngine()
    source = e.extract("Avoid roads with more than 30 cm of water.")
    candidate = e.extract("Avoid roads with more than 0.3 m of water.")
    assert v.verify(source, candidate).decision.value == "PASS"
