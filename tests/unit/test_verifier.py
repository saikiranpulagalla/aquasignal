import pytest

from signallock.contracts.extractor import HeuristicExtractor
from signallock.verification.engine import VerificationEngine


SOURCE = (
    "Residents in the eastern river district must shelter indoors until 6 PM. "
    "Do not enter the eastern underpass. Avoid roads with more than 30 cm of water, except emergency personnel."
)


@pytest.fixture()
def engine():
    return VerificationEngine()


def verify(source: str, candidate: str, engine):
    e = HeuristicExtractor()
    return engine.verify(e.extract(source), e.extract(candidate))


def test_identical_passes(engine):
    assert verify(SOURCE, SOURCE, engine).decision.value == "PASS"


def test_safe_paraphrase_passes(engine):
    candidate = SOURCE.replace("shelter indoors", "stay indoors")
    assert verify(SOURCE, candidate, engine).decision.value == "PASS"

@pytest.mark.parametrize(
    "candidate, expected_field",
    [
        (SOURCE.replace("Do not enter", "Enter"), "prohibited_action"),
        (SOURCE.replace("shelter indoors", "evacuate"), "required_action"),
        (SOURCE.replace("30 cm", "3 cm"), "quantity"),
        (SOURCE.replace("6 PM", "8 PM"), "required_action"),
        (SOURCE.replace("eastern river district", "western river district"), "affected_area"),
        (SOURCE.replace(", except emergency personnel", ""), "exception"),
        (SOURCE.replace("Residents", "Visitors", 1), "audience"),
    ],
)
def test_critical_mutations_do_not_pass(engine, candidate, expected_field):
    result = verify(SOURCE, candidate, engine)
    assert result.decision.value == "BLOCK"
    assert expected_field in result.critical_failures
