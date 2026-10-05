from fastapi.testclient import TestClient

from apps.api.main import app


client = TestClient(app)
SOURCE = "Residents must shelter indoors until 6 PM. Do not enter the eastern underpass."


def _source_contract():
    response = client.post("/api/extract", json={"text": SOURCE, "language": "en", "provider": "heuristic"})
    assert response.status_code == 200
    return response.json()


def test_frozen_source_contract_blocks_candidate_reversal():
    response = client.post(
        "/api/verify-contract",
        json={
            "source_text": SOURCE,
            "source_contract": _source_contract(),
            "candidate_text": "Residents must shelter indoors until 6 PM. Enter the eastern underpass.",
            "candidate_language": "en",
            "provider": "heuristic",
        },
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "BLOCK"


def test_frozen_source_contract_accepts_safe_rewrite():
    response = client.post(
        "/api/verify-contract",
        json={
            "source_text": SOURCE,
            "source_contract": _source_contract(),
            "candidate_text": "People living in the area must stay indoors until 18:00. Never enter the eastern underpass.",
            "candidate_language": "en",
            "provider": "heuristic",
        },
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "PASS"


def test_frozen_source_contract_rejects_tampered_evidence():
    contract = _source_contract()
    contract["required_actions"][0]["evidence"]["quote"] = "fabricated quote"
    response = client.post(
        "/api/verify-contract",
        json={
            "source_text": SOURCE,
            "source_contract": contract,
            "candidate_text": SOURCE,
            "candidate_language": "en",
            "provider": "heuristic",
        },
    )
    assert response.status_code == 422
    assert "provenance" in response.json()["detail"].lower()
