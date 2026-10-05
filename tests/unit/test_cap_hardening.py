from pathlib import Path

import pytest

from signallock.cap.mapper import cap_info_seed_contract
from signallock.cap.parser import parse_cap_xml

FIXTURE = Path(__file__).parents[1] / "fixtures" / "sample_cap.xml"


def test_cap_rejects_invalid_enumerations():
    xml = '''<alert><identifier>Z</identifier><sender>x@y</sender><sent>2026-09-10T12:00:00Z</sent><status>BANANA</status><msgType>Alert</msgType><scope>Public</scope></alert>'''
    with pytest.raises(ValueError, match="status"):
        parse_cap_xml(xml)


def test_cap_rejects_invalid_datetime():
    xml = '''<alert><identifier>Z</identifier><sender>x@y</sender><sent>not-a-time</sent><status>Actual</status><msgType>Alert</msgType><scope>Public</scope></alert>'''
    with pytest.raises(ValueError, match="sent"):
        parse_cap_xml(xml)


def test_cap_requires_sender_and_sent():
    with pytest.raises(ValueError, match="sender"):
        parse_cap_xml('<alert><identifier>Z</identifier><status>Actual</status><msgType>Alert</msgType><scope>Public</scope></alert>')


def test_instruction_semantics_are_part_of_seed_contract():
    alert = parse_cap_xml(FIXTURE.read_text(encoding="utf-8"))
    contract = cap_info_seed_contract(alert, alert.infos[0])
    assert contract.required_actions
    assert contract.prohibited_actions
    assert any(a.verb == "enter" for a in contract.prohibited_actions)

@pytest.mark.parametrize(
    "missing_fragment, expected_field",
    [
        ("<category>Met</category>", "category"),
        ("<event>Flood</event>", "event"),
        ("<urgency>Immediate</urgency>", "urgency"),
        ("<severity>Severe</severity>", "severity"),
        ("<certainty>Likely</certainty>", "certainty"),
    ],
)
def test_cap_info_requires_normative_core_fields(missing_fragment, expected_field):
    xml = """<alert>
      <identifier>Z</identifier><sender>x@y</sender><sent>2026-09-10T12:00:00Z</sent>
      <status>Actual</status><msgType>Alert</msgType><scope>Public</scope>
      <info><category>Met</category><event>Flood</event><urgency>Immediate</urgency>
      <severity>Severe</severity><certainty>Likely</certainty></info>
    </alert>""".replace(missing_fragment, "")
    with pytest.raises(ValueError, match=expected_field):
        parse_cap_xml(xml)


def test_cap_area_requires_area_description():
    xml = """<alert>
      <identifier>Z</identifier><sender>x@y</sender><sent>2026-09-10T12:00:00Z</sent>
      <status>Actual</status><msgType>Alert</msgType><scope>Public</scope>
      <info><category>Met</category><event>Flood</event><urgency>Immediate</urgency>
      <severity>Severe</severity><certainty>Likely</certainty><area></area></info>
    </alert>"""
    with pytest.raises(ValueError, match="areaDesc"):
        parse_cap_xml(xml)


def test_offline_non_english_cap_instruction_fails_closed():
    xml = """<alert>
      <identifier>Z</identifier><sender>x@y</sender><sent>2026-09-10T12:00:00Z</sent>
      <status>Actual</status><msgType>Alert</msgType><scope>Public</scope>
      <info><language>hi-IN</language><category>Met</category><event>Flood</event>
      <urgency>Immediate</urgency><severity>Severe</severity><certainty>Likely</certainty>
      <instruction>तुरंत ऊंची जगह पर जाएं।</instruction><area><areaDesc>पूर्वी क्षेत्र</areaDesc></area></info>
    </alert>"""
    alert = parse_cap_xml(xml)
    contract = cap_info_seed_contract(alert, alert.infos[0])
    assert contract.unresolved_operational_text == ["तुरंत ऊंची जगह पर जाएं।"]
