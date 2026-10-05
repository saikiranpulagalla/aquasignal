from signallock.contracts.extractor import HeuristicExtractor
from signallock.verification.engine import VerificationEngine


def test_partial_extraction_cannot_pass_when_unrecognized_operational_clause_exists():
    e = HeuristicExtractor()
    source = e.extract("Shelter indoors. Seek higher ground.")
    candidate = e.extract("Shelter indoors. Go to the basement.")
    assert source.unresolved_operational_text
    assert candidate.unresolved_operational_text
    assert VerificationEngine().verify(source, candidate).decision.value == "REVIEW"
