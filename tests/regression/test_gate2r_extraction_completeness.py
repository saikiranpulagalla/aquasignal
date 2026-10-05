from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app


CLIENT = TestClient(app)


CASES = [
    pytest.param(
        "A severe wildfire is affecting the eastern zone. Residents must evacuate.",
        "A minor wildfire is affecting the eastern zone. Residents must evacuate.",
        id="G2-F001-severity",
    ),
    pytest.param(
        "A wildfire is likely to affect the eastern zone. Residents must evacuate.",
        "A wildfire is unlikely to affect the eastern zone. Residents must evacuate.",
        id="G2-F002-certainty",
    ),
    pytest.param(
        "A chemical spill affects the eastern zone. Residents must evacuate.",
        "A gas leak affects the eastern zone. Residents must evacuate.",
        id="G2-F003-unsupported-hazard",
    ),
    pytest.param(
        "Residents must evacuate at 4 PM.",
        "Residents must evacuate at 8 PM.",
        id="G2-F004-action-time",
    ),
    pytest.param(
        "Residents must evacuate starting at 4 PM.",
        "Residents must evacuate starting at 8 PM.",
        id="G2-F005-start-time",
    ),
    pytest.param(
        "Residents must evacuate on Friday.",
        "Residents must evacuate on Saturday.",
        id="G2-F006-calendar-time",
    ),
    pytest.param(
        "Residents must evacuate when sirens sound.",
        "Residents must evacuate whether sirens sound or not.",
        id="G2-F007-condition",
    ),
]


def _verify_frozen(source: str, candidate: str) -> dict:
    authority = CLIENT.post(
        "/api/extract-authority",
        json={"text": source, "provider": "heuristic"},
    )
    assert authority.status_code == 200
    payload = authority.json()
    response = CLIENT.post(
        "/api/verify-contract",
        json={
            "source_text": source,
            "source_contract": payload["source_contract"],
            "authority_token": payload["authority_token"],
            "candidate_text": candidate,
            "candidate_language": "en",
            "provider": "heuristic",
        },
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize(("source", "candidate"), CASES)
def test_gate2r_original_false_passes_fail_closed_on_both_routes(source: str, candidate: str) -> None:
    direct = CLIENT.post(
        "/api/verify",
        json={"source_text": source, "candidate_text": candidate, "provider": "heuristic"},
    )
    assert direct.status_code == 200
    assert direct.json()["decision"] != "PASS"

    frozen = _verify_frozen(source, candidate)
    assert frozen["decision"] != "PASS"


def test_gate2r_existing_if_negation_control_still_blocks() -> None:
    source = "Residents must evacuate if sirens sound."
    candidate = "Residents must evacuate if sirens do not sound."
    direct = CLIENT.post(
        "/api/verify",
        json={"source_text": source, "candidate_text": candidate, "provider": "heuristic"},
    )
    assert direct.status_code == 200
    assert direct.json()["decision"] == "BLOCK"
    assert _verify_frozen(source, candidate)["decision"] == "BLOCK"
