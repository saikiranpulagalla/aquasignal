from copy import deepcopy

from fastapi.testclient import TestClient

from apps.aqua_api.main import app


client = TestClient(app)


def demo_context():
    response = client.get("/api/aqua/demo-context")
    assert response.status_code == 200
    return response.json()["context"]


def context_token_for(context: dict):
    response = client.get("/api/aqua/demo-context")
    demo = response.json()
    if demo["context"] == context:
        return demo["context_token"]
    raise AssertionError("test helper only signs the bundled demo context")


def freeze(source_text: str, context: dict, *, advisory_id: str = "demo", revision: int = 1):
    return client.post(
        "/api/aqua/authority",
        json={
            "source_text": source_text,
            "context": context,
            "context_token": context_token_for(context),
            "advisory_id": advisory_id,
            "revision": revision,
        },
    )


def verify(source: str, candidate: str, context: dict, *, revision: int = 1):
    authority = freeze(source, context, revision=revision)
    assert authority.status_code == 200, authority.text
    body = authority.json()
    return client.post(
        "/api/aqua/verify",
        json={
            "source_text": source,
            "source_contract": body["source_contract"],
            "authority_token": body["authority_token"],
            "context": context,
            "advisory_id": "demo",
            "revision": revision,
            "candidate_text": candidate,
        },
    )


def test_health_declares_deterministic_pass_path():
    body = client.get("/api/aqua/health").json()
    assert body["status"] == "ok"
    assert body["deterministic_pass_path"] is True
    assert body["semantic_profile"] == "freshwater-protective-communication-v1"


def test_end_to_end_time_reversal_blocks():
    context = demo_context()
    response = verify(
        "Visitors must avoid contact with Stream A after 18:00.",
        "Visitors must avoid contact with Stream A before 18:00.",
        context,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "BLOCK"
    assert body["display_decision"] == "CRITICAL DRIFT"
    assert body["integrity_receipt"]["decision"] == "BLOCK"


def test_end_to_end_audience_loss_blocks():
    response = verify(
        "Keep children and pets away from Stream A until 18:00.",
        "Keep children away from Stream A until 18:00.",
        demo_context(),
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "BLOCK"


def test_end_to_end_flow_direction_reversal_blocks_without_false_stream_water_site():
    response = verify(
        "Avoid direct contact with stream water downstream of Bridge A until 18:00.",
        "Avoid direct contact with stream water upstream of Bridge A until 18:00.",
        demo_context(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "BLOCK"
    assert any(s["field"] == "place_relation" and s["status"] == "FAIL" for s in body["signals"])


def test_end_to_end_clean_clock_equivalence_passes():
    response = verify(
        "Visitors must avoid contact with Stream A until 6 PM.",
        "Visitors must avoid contact with Stream A until 18:00.",
        demo_context(),
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "PASS"


def test_end_to_end_added_advice_blocks():
    response = verify(
        "Avoid direct contact with Stream A until 18:00.",
        "Avoid direct contact with Stream A until 18:00. Boil the water for at least 1 minute before drinking.",
        demo_context(),
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "BLOCK"


def test_context_tampering_invalidates_authority_token():
    context = demo_context()
    source = "Visitors must avoid contact with Stream A until 18:00."
    authority = freeze(source, context).json()
    changed = deepcopy(context)
    changed["indicators"] = changed["indicators"] + ["tampered"]
    response = client.post(
        "/api/aqua/verify",
        json={
            "source_text": source,
            "source_contract": authority["source_contract"],
            "authority_token": authority["authority_token"],
            "context": changed,
            "advisory_id": "demo",
            "revision": 1,
            "candidate_text": source,
        },
    )
    assert response.status_code == 409


def test_context_site_mismatch_forces_source_review():
    context = demo_context()
    response = freeze("Avoid direct contact with Stream B until 18:00.", context)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["state"] == "SOURCE_REVIEW"
    assert detail["context_alignment"] == "MISMATCH"


def test_revision_change_invalidates_old_token():
    context = demo_context()
    source = "Avoid direct contact with Stream A until 18:00."
    authority = freeze(source, context, revision=1).json()
    response = client.post(
        "/api/aqua/verify",
        json={
            "source_text": source,
            "source_contract": authority["source_contract"],
            "authority_token": authority["authority_token"],
            "context": context,
            "advisory_id": "demo",
            "revision": 2,
            "candidate_text": source,
        },
    )
    assert response.status_code == 409


def test_homepage_has_accessibility_and_human_authority_copy():
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert 'class="skip-link"' in html
    assert 'aria-live="polite"' in html
    assert '<label for="sourceText">' in html
    assert 'final publication authority remains human' in html


def test_security_headers_present_on_homepage():
    response = client.get("/")
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_profile_endpoint_declares_bounded_scope_and_human_authority():
    response = client.get("/api/aqua/profile")
    assert response.status_code == 200
    body = response.json()
    assert body["automatic_pass_policy"] == "deterministic-only"
    assert body["unsupported_behavior"] == "REVIEW"
    assert body["risk_inference"] is False
    assert body["publication_authority"] == "human"


def test_generic_fhir_does_not_claim_oneaquahealth_conformance():
    response = client.post(
        "/api/aqua/context/fhir",
        json={
            "resource": {
                "resourceType": "Observation",
                "id": "obs-1",
                "status": "final",
                "code": {"text": "Environmental indicator"},
                "subject": {"display": "Stream A"},
            },
            "synthetic_demo": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["compatibility"] == "generic-environmental-fhir"
    assert "no OneAquaHealth profile conformance is claimed" in response.json()["claim"]


def test_release_evidence_endpoint_is_hash_bound_and_qualified():
    response = client.get("/api/aqua/release-evidence")
    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is True
    assert body["qualified"] is True
    assert body["holdout"] == "aqua-holdout-v17"
    assert body["metrics"]["unsafe_pass"] == 0
    assert body["metrics"]["clean_pass"] == body["metrics"]["clean_total"]
