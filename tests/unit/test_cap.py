from pathlib import Path

import pytest

from signallock.cap.mapper import cap_info_seed_contract
from signallock.cap.parser import MAX_CAP_BYTES, parse_cap_xml
from signallock.contracts.schema import ActionType, Severity, Urgency

FIXTURE = Path(__file__).parents[1] / "fixtures" / "sample_cap.xml"


def test_parse_multilingual_cap():
    alert = parse_cap_xml(FIXTURE.read_text(encoding="utf-8"))
    assert alert.identifier == "TEST-001"
    assert len(alert.infos) == 2
    assert alert.infos[0].language == "en-IN"
    assert alert.infos[1].language == "hi-IN"
    assert alert.infos[0].areas == ["Eastern River District"]


def test_cap_seed_contract():
    alert = parse_cap_xml(FIXTURE.read_text(encoding="utf-8"))
    contract = cap_info_seed_contract(alert, alert.infos[0])
    assert contract.urgency == Urgency.IMMEDIATE
    assert contract.severity == Severity.SEVERE
    assert [a.type for a in contract.required_actions] == [ActionType.SHELTER]
    assert any(a.type == ActionType.AVOID for a in contract.prohibited_actions)
    assert contract.affected_areas == ["Eastern River District"]


def test_malformed_cap_is_controlled():
    with pytest.raises(ValueError):
        parse_cap_xml("<alert><identifier>x")


def test_missing_identifier_rejected():
    with pytest.raises(ValueError):
        parse_cap_xml("<alert><status>Actual</status></alert>")


def test_wrong_root_rejected():
    with pytest.raises(ValueError):
        parse_cap_xml("<info><identifier>x</identifier></info>")


def test_oversize_rejected():
    with pytest.raises(ValueError):
        parse_cap_xml(b"x" * (MAX_CAP_BYTES + 1))
