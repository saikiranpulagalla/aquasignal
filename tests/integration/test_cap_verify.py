from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)
FIXTURE = Path(__file__).parents[1] / "fixtures" / "sample_cap.xml"


def test_cap_to_cap_verification_uses_instruction_semantics():
    source = FIXTURE.read_text(encoding="utf-8")
    candidate = source.replace("Do not enter the eastern underpass.", "Enter the eastern underpass.")
    response = client.post("/api/verify-cap", json={"source_xml": source, "candidate_xml": candidate})
    assert response.status_code == 200
    assert response.json()["decision"] == "BLOCK"
