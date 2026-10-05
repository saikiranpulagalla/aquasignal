import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

import apps.api.main as api
from apps.api.main import app


def _request(host="203.0.113.10"):
    return Request({"type":"http","method":"POST","path":"/api/extract","headers":[],"client":(host,12345),"server":("example",443),"scheme":"https","query_string":b""})


def test_public_live_provider_is_fail_closed_without_demo_token(monkeypatch):
    monkeypatch.setattr(api, "_LIVE_PROVIDER_TOKEN", None)
    api._LIVE_CALLS.clear()
    with pytest.raises(HTTPException) as exc:
        api._guard_live_provider(_request(), "openai", None)
    assert exc.value.status_code == 403


def test_public_live_provider_requires_exact_configured_token(monkeypatch):
    monkeypatch.setattr(api, "_LIVE_PROVIDER_TOKEN", "secret")
    monkeypatch.setattr(api, "_AUTHORITY_SECRET_CONFIGURED", True)
    api._LIVE_CALLS.clear()
    with pytest.raises(HTTPException) as exc:
        api._guard_live_provider(_request(), "openai", "wrong")
    assert exc.value.status_code == 403
    api._guard_live_provider(_request(), "openai", "secret")


def test_server_issued_authority_token_round_trip_and_tamper_detection():
    client = TestClient(app)
    source = "Residents must shelter indoors."
    issued = client.post("/api/extract-authority", json={"text":source,"language":"en","provider":"heuristic"})
    assert issued.status_code == 200
    body = issued.json()
    ok = client.post("/api/verify-contract", json={
        "source_text":source,"source_contract":body["source_contract"],"authority_token":body["authority_token"],
        "candidate_text":"Residents must shelter indoors.","candidate_language":"en","provider":"heuristic",
    })
    assert ok.status_code == 200 and ok.json()["decision"] == "PASS"
    tampered = body["source_contract"]
    tampered["audience"] = ["visitors"]
    bad = client.post("/api/verify-contract", json={
        "source_text":source,"source_contract":tampered,"authority_token":body["authority_token"],
        "candidate_text":"Visitors must shelter indoors.","candidate_language":"en","provider":"heuristic",
    })
    assert bad.status_code == 422


def test_browser_has_stale_verdict_generation_guard():
    text = open("web/app.js", encoding="utf-8").read()
    assert "verificationSnapshot" in text
    assert "snapshotStillCurrent" in text
    assert "verifyGeneration" in text
