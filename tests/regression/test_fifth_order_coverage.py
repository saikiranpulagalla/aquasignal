import pytest

from signallock.cap.parser import parse_cap_xml
import pytest
from signallock.cap.verifier import verify_cap_alerts
from signallock.contracts.extractor import HeuristicExtractor
from signallock.verification.engine import VerificationEngine


@pytest.mark.parametrize("phrase", [
    "relocate livestock", "keep clear of waterways", "remain off bridges",
    "secure loose outdoor objects", "isolate the supply", "return only when cleared",
])
def test_mixed_unsupported_operational_directive_cannot_evaporate_to_pass(phrase):
    source = f"Residents must evacuate and {phrase}."
    candidate = "Residents must evacuate."
    result = VerificationEngine().verify(HeuristicExtractor().extract(source), HeuristicExtractor().extract(candidate))
    assert result.decision.value != "PASS"


def _cap(*, onset="2026-01-01T01:00:00+00:00", categories=("Met", "Safety"), polygon="10,10 10,11 11,11 10,10"):
    cats = "".join(f"<category>{value}</category>" for value in categories)
    return f'''<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>A</identifier><sender>a</sender><sent>2026-01-01T00:00:00+00:00</sent><status>Actual</status><msgType>Alert</msgType><scope>Public</scope><info>{cats}<event>Flood</event><urgency>Immediate</urgency><severity>Severe</severity><certainty>Likely</certainty><onset>{onset}</onset><effective>2026-01-01T00:30:00+00:00</effective><expires>2026-01-02T00:00:00+00:00</expires><instruction>Residents must evacuate.</instruction><area><areaDesc>Zone A</areaDesc><polygon>{polygon}</polygon></area></info></alert>'''


def test_cap_onset_change_cannot_pass():
    source = parse_cap_xml(_cap(), profile_strict=True)
    candidate = parse_cap_xml(_cap(onset="2026-01-01T05:00:00+00:00"), profile_strict=True)
    assert verify_cap_alerts(source, candidate).decision.value != "PASS"


def test_cap_equivalent_ordering_and_polygon_winding_pass():
    source = parse_cap_xml(_cap(), profile_strict=True)
    candidate = parse_cap_xml(_cap(categories=("Safety", "Met"), polygon="11,11 10,11 10,10 11,11"), profile_strict=True)
    assert verify_cap_alerts(source, candidate).decision.value == "PASS"


def test_mixed_boolean_topology_is_reviewed_not_flattened_to_pass():
    source = "Residents must evacuate or shelter indoors, and boil water."
    rewired = "Residents must evacuate and shelter indoors, or boil water."
    result = VerificationEngine().verify(HeuristicExtractor().extract(source), HeuristicExtractor().extract(rewired))
    assert result.decision.value != "PASS"

def test_cap_duplicate_safety_field_is_rejected_by_strict_profile():
    source = _cap()
    duplicate = source.replace("<severity>Severe</severity>", "<severity>Severe</severity><severity>Extreme</severity>")
    with pytest.raises(ValueError, match="severity.*duplicated"):
        parse_cap_xml(duplicate, profile_strict=True)