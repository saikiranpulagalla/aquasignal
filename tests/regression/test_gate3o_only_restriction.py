from __future__ import annotations

import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from apps.api import main as api
from signallock.contracts.extractor import HeuristicExtractor
from signallock.contracts.schema import Decision
from signallock.providers.openai_http import OpenAIResponsesProvider, contract_from_provider_output
from signallock.verification.engine import VerificationEngine


CLIENT = TestClient(api.app)
E = HeuristicExtractor()
V = VerificationEngine()
SOURCE = "Only emergency personnel must evacuate Zone A."
CANDIDATE = "Emergency personnel must evacuate Zone A."


def _verify(source: str, candidate: str, provider: str = "heuristic"):
    return CLIENT.post(
        "/api/verify",
        json={
            "source_text": source,
            "candidate_text": candidate,
            "source_language": "en",
            "candidate_language": "en",
            "provider": provider,
        },
    )


def _frozen(source: str, candidate: str):
    authority = CLIENT.post(
        "/api/extract-authority",
        json={"text": source, "language": "en", "provider": "heuristic"},
    )
    assert authority.status_code == 200, authority.text
    data = authority.json()
    response = CLIENT.post(
        "/api/verify-contract",
        json={
            "source_text": source,
            "source_contract": data["source_contract"],
            "authority_token": data["authority_token"],
            "candidate_text": candidate,
            "candidate_language": "en",
            "provider": "heuristic",
        },
    )
    return authority, response


def _cap(instruction: str) -> str:
    return f'''<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>A</identifier><sender>a</sender><sent>2026-01-01T00:00:00+00:00</sent><status>Actual</status><msgType>Alert</msgType><scope>Public</scope><info><language>en</language><category>Safety</category><event>Flood</event><urgency>Immediate</urgency><severity>Severe</severity><certainty>Likely</certainty><instruction>{instruction}</instruction><area><areaDesc>Zone A</areaDesc></area></info></alert>'''


def _provider_payload(text: str, source_id: str) -> dict:
    contract = E.extract(text, language="en", source_id=source_id)
    return contract.model_dump(mode="json")


def _install_provider_that_drops_only(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    api._LIVE_CALLS.clear()

    async def fake_request(self, payload):
        user = payload["input"][1]["content"]
        alert = user.split("ALERT:\n", 1)[1]
        represented = alert.replace("Only emergency personnel", "Emergency personnel")
        out = _provider_payload(represented, "provider")
        # Re-anchor evidence to the real raw text for the semantic fact that is returned.
        for action in out.get("required_actions", []):
            ev = action.get("evidence")
            if ev and ev.get("quote"):
                quote = ev["quote"]
                pos = alert.find(quote)
                if pos >= 0:
                    ev["start_char"] = pos
                    ev["end_char"] = pos + len(quote)
        return {
            "id": "resp_gate3o",
            "model": "test-model",
            "status": "completed",
            "store": False,
            "output": [{"content": [{"type": "output_text", "text": json.dumps(out)}]}],
        }

    monkeypatch.setattr(OpenAIResponsesProvider, "_request", fake_request)


def test_original_direct_route_never_passes() -> None:
    response = _verify(SOURCE, CANDIDATE)
    assert response.status_code == 200
    assert response.json()["decision"] != "PASS"


def test_original_frozen_authority_route_never_passes() -> None:
    _, response = _frozen(SOURCE, CANDIDATE)
    assert response.status_code == 200
    assert response.json()["decision"] != "PASS"


def test_extractor_preserves_unrepresented_audience_exclusivity() -> None:
    contract = E.extract(SOURCE)
    assert contract.audience == ["emergency personnel"]
    assert contract.unresolved_operational_text
    assert any("Only emergency personnel" in item for item in contract.unresolved_operational_text)


ORIGINAL_SIBLINGS = [
    ("Only residents must evacuate Zone A.", "Residents must evacuate Zone A."),
    ("Only visitors must evacuate Zone A.", "Visitors must evacuate Zone A."),
    ("Only drivers should avoid the roads.", "Drivers should avoid the roads."),
    ("Only students must evacuate Zone A.", "Students must evacuate Zone A."),
    ("Only emergency personnel should shelter indoors.", "Emergency personnel should shelter indoors."),
    ("Only residents may shelter indoors.", "Residents may shelter indoors."),
    ("Residents must evacuate Zone A.", "Only residents must evacuate Zone A."),
    ("Only drivers must avoid bridges.", "Drivers must avoid bridges."),
    ("Only non-residents must evacuate Zone A.", "Non-residents must evacuate Zone A."),
    ("Only residents in Zone A must evacuate.", "Residents in Zone A must evacuate."),
]


@pytest.mark.parametrize(("source", "candidate"), ORIGINAL_SIBLINGS)
def test_original_siblings_never_pass(source: str, candidate: str) -> None:
    response = _verify(source, candidate)
    assert response.status_code == 200
    assert response.json()["decision"] != "PASS"


@pytest.mark.parametrize(
    ("source", "candidate"),
    [
        ("Only residents must evacuate.", "Residents must evacuate."),
        ("Residents must evacuate.", "Only residents must evacuate."),
        ("Only residents must evacuate.", "Only visitors must evacuate."),
        ("Only residents must evacuate.", "Only residents may evacuate."),
        ("Only residents in Zone A must evacuate.", "Only residents in Zone B must evacuate."),
        ("Only residents must evacuate.", "Only residents must shelter indoors."),
    ],
)
def test_restriction_asymmetry_and_neighbor_drift_never_pass(source: str, candidate: str) -> None:
    response = _verify(source, candidate)
    assert response.status_code == 200
    assert response.json()["decision"] != "PASS"


@pytest.mark.parametrize(
    "text",
    [
        "Residents must only evacuate Zone A.",
        "Residents only must evacuate Zone A.",
        "Emergency personnel only may enter Zone A.",
        "Evacuate Zone A only.",
        "This warning applies to Zone A only.",
        "Use Route 5 only.",
        "Shelter in Building A only.",
        "Avoid the north bridge only.",
    ],
)
def test_unrepresented_operational_only_forms_are_unresolved(text: str) -> None:
    contract = E.extract(text)
    assert contract.unresolved_operational_text, contract.model_dump(mode="json")


@pytest.mark.parametrize(
    "text",
    [
        "Residents must evacuate only if sirens sound.",
        "Only if sirens sound, residents must evacuate Zone A.",
        "Residents must evacuate only if officials order evacuation.",
    ],
)
def test_only_if_remains_condition_not_audience_exclusivity(text: str) -> None:
    contract = E.extract(text)
    assert contract.required_actions
    assert any(a.condition and "only if" in a.condition.casefold() for a in contract.required_actions)
    assert not contract.unresolved_operational_text


@pytest.mark.parametrize(
    ("source", "candidate"),
    [
        ("Residents must evacuate only if sirens sound.", "Residents must evacuate if sirens sound."),
        ("Residents must evacuate only if sirens sound.", "Residents must evacuate only if sirens do not sound."),
    ],
)
def test_only_if_semantic_change_never_passes(source: str, candidate: str) -> None:
    response = _verify(source, candidate)
    assert response.status_code == 200
    assert response.json()["decision"] != "PASS"


@pytest.mark.parametrize(
    "text",
    [
        "Residents must evacuate only before 6 PM.",
        "Residents must evacuate only after 6 PM.",
        "Residents must evacuate only at 6 PM.",
        "Residents must evacuate only until 8 PM.",
        "Residents must evacuate only on Friday.",
    ],
)
def test_temporal_only_does_not_force_unresolved_when_time_is_bound(text: str) -> None:
    contract = E.extract(text)
    assert contract.required_actions
    assert contract.required_actions[0].temporal_constraints
    assert not contract.unresolved_operational_text


@pytest.mark.parametrize(
    "text",
    [
        "For information only, call 311.",
        "For more information only, call 311.",
    ],
)
def test_confident_harmless_only_metadata_stays_non_operational(text: str) -> None:
    contract = E.extract(text)
    assert not contract.unresolved_operational_text


def test_restriction_attachment_swap_never_passes() -> None:
    source = "Only residents must evacuate Zone A. Visitors must shelter indoors."
    candidate = "Residents must evacuate Zone A. Only visitors must shelter indoors."
    response = _verify(source, candidate)
    assert response.status_code == 200
    assert response.json()["decision"] != "PASS"


def test_multilingual_composition_preserves_both_uncertainties() -> None:
    source = "Only residents must evacuate Zone A. निवासी घर में रहें।"
    candidate = "Residents must evacuate Zone A."
    response = _verify(source, candidate)
    assert response.status_code == 200
    assert response.json()["decision"] != "PASS"
    contract = E.extract(source)
    assert contract.unresolved_operational_text


def test_mocked_openai_omission_of_exclusivity_never_passes(monkeypatch) -> None:
    _install_provider_that_drops_only(monkeypatch)
    response = _verify(SOURCE, CANDIDATE, provider="openai")
    assert response.status_code == 200, response.text
    assert response.json()["decision"] != "PASS"


def test_provider_coverage_marks_dropped_exclusivity_unresolved() -> None:
    raw = SOURCE
    payload = _provider_payload(CANDIDATE, "provider")
    # Re-anchor action evidence from candidate representation to raw source.
    action = payload["required_actions"][0]
    quote = action["evidence"]["quote"]
    pos = raw.find(quote)
    assert pos >= 0
    action["evidence"]["start_char"] = pos
    action["evidence"]["end_char"] = pos + len(quote)
    contract = contract_from_provider_output(json.dumps(payload), raw, language="en", source_id="provider")
    assert contract.unresolved_operational_text
    assert V.verify(contract, contract).decision == Decision.REVIEW


def test_cap_only_deletion_never_passes() -> None:
    response = CLIENT.post(
        "/api/verify-cap",
        json={"source_xml": _cap(SOURCE), "candidate_xml": _cap(CANDIDATE)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["decision"] != "PASS"


def test_signed_unresolved_restriction_cannot_be_stripped() -> None:
    authority = CLIENT.post(
        "/api/extract-authority",
        json={"text": SOURCE, "language": "en", "provider": "heuristic"},
    )
    assert authority.status_code == 200
    data = authority.json()
    assert data["source_contract"]["unresolved_operational_text"]
    tampered = deepcopy(data["source_contract"])
    tampered["unresolved_operational_text"] = []
    response = CLIENT.post(
        "/api/verify-contract",
        json={
            "source_text": SOURCE,
            "source_contract": tampered,
            "authority_token": data["authority_token"],
            "candidate_text": SOURCE,
            "candidate_language": "en",
            "provider": "heuristic",
        },
    )
    assert response.status_code == 422


def test_leading_time_does_not_absorb_following_audience_only() -> None:
    source = "At 6 PM, only residents must evacuate Zone A."
    candidate = "At 6 PM, residents must evacuate Zone A."
    source_contract = E.extract(source)
    assert source_contract.unresolved_operational_text
    response = _verify(source, candidate)
    assert response.status_code == 200
    assert response.json()["decision"] != "PASS"


@pytest.mark.parametrize(
    ("source", "candidate"),
    [
        ("Solely residents must evacuate Zone A.", "Residents must evacuate Zone A."),
        ("Exclusively visitors must shelter indoors.", "Visitors must shelter indoors."),
        ("Access is restricted to emergency personnel.", "Access is open to emergency personnel."),
        ("Access is limited to emergency personnel.", "Access is available to emergency personnel."),
    ],
)
def test_neighbor_restrictive_synonyms_fail_closed(source: str, candidate: str) -> None:
    source_contract = E.extract(source)
    assert source_contract.unresolved_operational_text
    response = _verify(source, candidate)
    assert response.status_code == 200
    assert response.json()["decision"] != "PASS"


@pytest.mark.parametrize(
    "text",
    [
        "This is only a test message.",
        "Administrative use only.",
        "This phone number is for information only.",
        "Source attribution is for reference only.",
    ],
)
def test_harmless_only_metadata_does_not_create_extractor_uncertainty(text: str) -> None:
    contract = E.extract(text)
    assert not contract.unresolved_operational_text
