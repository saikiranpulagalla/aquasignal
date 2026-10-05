import pytest

from signallock.contracts.extractor import HeuristicExtractor
from signallock.contracts.schema import Action, ActionType, EvidenceSpan, Modality, SafetyContract
from signallock.verification.engine import VerificationEngine


@pytest.mark.parametrize("language,quote", [
    ("hi", "निवासियों को तुरंत बाहर निकलना चाहिए।"),
    ("te", "నివాసితులు వెంటనే బయటకు వెళ్లాలి."),
])
@pytest.mark.parametrize("field,value", [("scoped_audience", ["visitors"]), ("scoped_areas", ["Zone B"]), ("condition", "if officials order it")])
def test_native_structured_scope_claims_cannot_upgrade_to_pass(language, quote, field, value):
    fields = {field: value}
    candidate = SafetyContract(
        language=language,
        required_actions=[Action(
            type=ActionType.EVACUATE, verb="evacuate", modality=Modality.MUST,
            evidence=EvidenceSpan(quote=quote, start_char=0, end_char=len(quote)), **fields,
        )],
    )
    source = HeuristicExtractor().extract("Residents must evacuate.")
    assert VerificationEngine().verify(source, candidate).decision.value != "PASS"
