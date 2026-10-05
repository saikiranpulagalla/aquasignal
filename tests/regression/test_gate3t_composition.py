from __future__ import annotations

import json
from copy import deepcopy

from fastapi.testclient import TestClient

from apps.api.main import app
from signallock.contracts.extractor import HeuristicExtractor
from signallock.contracts.schema import Decision
from signallock.providers.openai_http import contract_from_provider_output
from signallock.verification.engine import VerificationEngine


CLIENT = TestClient(app)
E = HeuristicExtractor()
V = VerificationEngine()
SOURCE = "At 6 PM, residents must evacuate Zone A."
CANDIDATE = "At 8 PM, residents must evacuate Zone A."


def _provider_contract(raw: str, *, omit_time: bool = False, override_time: str | None = None):
    payload = E.extract(raw, source_id="provider").model_dump(mode="json")
    action = payload["required_actions"][0]
    if omit_time:
        action["deadline"] = None
        action["temporal_operator"] = None
        action["temporal_constraints"] = []
    if override_time is not None:
        action["deadline"] = override_time
        action["temporal_operator"] = "AT"
        action["temporal_constraints"] = [{"operator": "AT", "time": override_time}]
    return contract_from_provider_output(json.dumps(payload), raw, language="en", source_id="provider")


def test_provider_correct_preposed_time_reaches_deterministic_comparison() -> None:
    source = _provider_contract(SOURCE)
    candidate = _provider_contract(CANDIDATE)
    assert not source.unresolved_operational_text
    assert not candidate.unresolved_operational_text
    assert V.verify(source, candidate).decision == Decision.BLOCK


def test_provider_omitted_preposed_time_becomes_uncertainty_not_pass() -> None:
    source = _provider_contract(SOURCE, omit_time=True)
    candidate = _provider_contract(CANDIDATE, omit_time=True)
    assert source.unresolved_operational_text
    assert candidate.unresolved_operational_text
    assert V.verify(source, candidate).decision != Decision.PASS


def test_provider_hallucinated_temporal_value_is_not_trusted() -> None:
    contract = _provider_contract(SOURCE, override_time="8 PM")
    assert contract.unresolved_operational_text
    assert V.verify(contract, contract).decision == Decision.REVIEW


def test_frozen_authority_after_repair_blocks_preposed_time_change() -> None:
    authority = CLIENT.post(
        "/api/extract-authority",
        json={"text": SOURCE, "language": "en", "provider": "heuristic"},
    )
    assert authority.status_code == 200, authority.text
    data = authority.json()
    action = data["source_contract"]["required_actions"][0]
    assert action["temporal_operator"] == "AT"
    assert action["temporal_constraints"] == [{"operator": "AT", "time": "6 PM"}]

    response = CLIENT.post(
        "/api/verify-contract",
        json={
            "source_text": SOURCE,
            "source_contract": data["source_contract"],
            "authority_token": data["authority_token"],
            "candidate_text": CANDIDATE,
            "candidate_language": "en",
            "provider": "heuristic",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "BLOCK"


def test_signed_temporal_representation_cannot_be_changed_under_same_token() -> None:
    authority = CLIENT.post(
        "/api/extract-authority",
        json={"text": SOURCE, "language": "en", "provider": "heuristic"},
    ).json()
    tampered = deepcopy(authority["source_contract"])
    action = tampered["required_actions"][0]
    action["deadline"] = "8 PM"
    action["temporal_operator"] = "AT"
    action["temporal_constraints"] = [{"operator": "AT", "time": "8 PM"}]
    response = CLIENT.post(
        "/api/verify-contract",
        json={
            "source_text": SOURCE,
            "source_contract": tampered,
            "authority_token": authority["authority_token"],
            "candidate_text": SOURCE,
            "candidate_language": "en",
            "provider": "heuristic",
        },
    )
    assert response.status_code == 422


def _cap(instruction: str) -> str:
    return f'''<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>A</identifier><sender>a</sender><sent>2026-01-01T00:00:00+00:00</sent><status>Actual</status><msgType>Alert</msgType><scope>Public</scope><info><language>en</language><category>Safety</category><event>Flood</event><urgency>Immediate</urgency><severity>Severe</severity><certainty>Likely</certainty><instruction>{instruction}</instruction><area><areaDesc>Zone A</areaDesc></area></info></alert>'''


def test_cap_preposed_instruction_temporal_drift_blocks() -> None:
    response = CLIENT.post(
        "/api/verify-cap",
        json={"source_xml": _cap(SOURCE), "candidate_xml": _cap(CANDIDATE)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "BLOCK"


def test_cap_identical_preposed_instruction_time_remains_pass() -> None:
    response = CLIENT.post(
        "/api/verify-cap",
        json={"source_xml": _cap(SOURCE), "candidate_xml": _cap(SOURCE)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "PASS"
