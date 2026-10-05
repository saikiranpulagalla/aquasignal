import pytest

from signallock.contracts.extractor import HeuristicExtractor
from signallock.contracts.provenance import validate_provenance
from signallock.verification.engine import VerificationEngine


@pytest.mark.parametrize("source,candidate", [
    ("Residents must boil water.", "Water must be boiled by residents."),
    ("Drivers must avoid the bridge.", "The bridge must be avoided by drivers."),
    ("Residents must drink water.", "Water must be drunk by residents."),
    ("Residents in Zone A must boil water by 6 PM.", "Water must be boiled by residents in Zone A by 6 PM."),
    ("Residents must boil water for 5 minutes.", "Water must be boiled by residents for 5 minutes."),
    ("Residents must boil water except for emergency personnel.", "Water must be boiled by residents except for emergency personnel."),
    ("Residents must boil water if officials order it.", "Water must be boiled by residents if officials order it."),
])
def test_supported_passive_preserves_contract_and_original_provenance(source, candidate):
    extractor = HeuristicExtractor()
    contract = extractor.extract(candidate)
    assert not validate_provenance(candidate, contract, require_p0=True)
    assert not contract.unresolved_operational_text
    assert VerificationEngine().verify(extractor.extract(source), contract).decision.value == "PASS"


@pytest.mark.parametrize("candidate", [
    "Water must not be boiled by residents.",
    "Water may be boiled by residents.",
    "Water should be boiled by residents.",
    "Water must be boiled by visitors.",
    "Water must be drunk by residents.",
    "Water must be boiled by residents in Zone B.",
    "Water must be boiled by residents by 7 PM.",
    "Water must be boiled by residents except for emergency personnel.",
    'The poster says "Water must be boiled by residents."',
    "Water must be boiled.",
    "Water must be boiled by residents and handled appropriately.",
])
def test_passive_extension_does_not_approve_changed_or_unresolved_directives(candidate):
    extractor = HeuristicExtractor()
    result = VerificationEngine().verify(extractor.extract("Residents must boil water."), extractor.extract(candidate))
    assert result.decision.value != "PASS"
