from fastapi.testclient import TestClient

from apps.api.main import app


client = TestClient(app)

SOURCE = (
    "Residents in the eastern river district must shelter indoors until 6 PM. "
    "Do not enter the eastern underpass. Avoid roads with more than 30 cm of water, except emergency personnel."
)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_extract_endpoint():
    response = client.post("/api/extract", json={"text": SOURCE})
    assert response.status_code == 200
    assert response.json()["required_actions"]


def test_verify_endpoint_blocks_reversal():
    response = client.post("/api/verify", json={
        "source_text": SOURCE,
        "candidate_text": SOURCE.replace("Do not enter", "Enter"),
    })
    assert response.status_code == 200
    assert response.json()["decision"] == "BLOCK"


def test_translate_requires_live_provider():
    response = client.post("/api/transform", json={"text": SOURCE, "mode": "translate", "language": "hi"})
    assert response.status_code == 422
    assert "will not fake" in response.json()["detail"]


def test_benchmark_endpoint():
    response = client.get("/api/benchmark")
    assert response.status_code == 200
    body = response.json()
    assert body["metrics"]["unsafe_total"] > 0
