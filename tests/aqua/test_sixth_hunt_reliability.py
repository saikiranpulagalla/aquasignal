from __future__ import annotations

from fastapi.testclient import TestClient

from apps.aqua_api.main import app
from aquasignal.domain.freshwater import FreshwaterExtractor, assess_source_readiness
from aquasignal.integrity.verifier import AquaVerificationEngine


extractor = FreshwaterExtractor()
verifier = AquaVerificationEngine()
client = TestClient(app, raise_server_exceptions=False)


def _decision(source: str, candidate: str) -> str:
    return verifier.verify(extractor.extract(source), extractor.extract(candidate)).decision.value


def test_unpunctuated_multiline_bullets_are_distinct_supported_directives():
    text = "- Do not swim in Stream A until 18:00\n- Do not fish in Stream B until 19:00"
    contract = extractor.extract(text)
    assert assess_source_readiness(contract).ready
    assert [(a.verb, a.scoped_areas) for a in contract.prohibited_actions] == [
        ("swim", ["stream A"]),
        ("fish", ["stream B"]),
    ]
    for action in contract.prohibited_actions:
        evidence = action.evidence
        assert evidence is not None
        assert text[evidence.start_char:evidence.end_char] == evidence.quote


def test_unpunctuated_numbered_list_is_equivalent_to_sentence_form():
    source = "1) Do not swim in Stream A until 18:00\n2) Do not fish in Stream B until 19:00"
    candidate = "Do not swim in Stream A until 18:00. Do not fish in Stream B until 19:00."
    assert assess_source_readiness(extractor.extract(source)).ready
    assert _decision(source, candidate) == "PASS"


def test_wrapped_bullet_item_plus_next_unpunctuated_item_preserves_boundaries():
    source = (
        "- Visitors must avoid contact with\n"
        "  Stream A until 18:00\n"
        "- Do not fish in Stream B until 19:00"
    )
    candidate = (
        "Visitors must avoid contact with Stream A until 18:00. "
        "Do not fish in Stream B until 19:00."
    )
    assert assess_source_readiness(extractor.extract(source)).ready
    assert _decision(source, candidate) == "PASS"


def test_unpunctuated_list_with_unsupported_second_directive_stays_fail_closed():
    source = "- Do not swim in Stream A until 18:00\n- Wear gloves"
    readiness = assess_source_readiness(extractor.extract(source))
    assert not readiness.ready
    assert any("unresolved" in reason.casefold() for reason in readiness.reasons)


def test_static_assets_require_revalidation_to_avoid_stale_demo_code():
    for path in ("/", "/app.js", "/app.css"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers.get("cache-control") == "no-cache"


def test_api_method_mismatch_remains_controlled_and_no_store():
    response = client.get("/api/aqua/authority")
    assert response.status_code == 405
    assert response.headers.get("cache-control") == "no-store"
    assert response.headers.get("content-security-policy")


def test_cross_directive_time_swap_is_confirmed_relational_drift():
    source = "Do not swim in Stream A until 18:00. Do not swim in Stream B until 19:00."
    candidate = "Do not swim in Stream A until 19:00. Do not swim in Stream B until 18:00."
    assert assess_source_readiness(extractor.extract(source)).ready
    assert _decision(source, candidate) == "BLOCK"


def test_cross_directive_site_swap_is_confirmed_relational_drift():
    source = "Do not swim in Stream A until 18:00. Do not fish in Stream B until 19:00."
    candidate = "Do not swim in Stream B until 18:00. Do not fish in Stream A until 19:00."
    assert assess_source_readiness(extractor.extract(source)).ready
    assert _decision(source, candidate) == "BLOCK"


def test_cross_directive_clause_reordering_remains_clean():
    source = "Do not swim in Stream A until 18:00. Do not fish in Stream B until 19:00."
    candidate = "Do not fish in Stream B until 19:00. Do not swim in Stream A until 18:00."
    assert _decision(source, candidate) == "PASS"


def test_cross_directive_safe_clock_equivalence_does_not_trigger_rewire():
    source = "Do not swim in Stream A until 6 PM. Do not fish in Stream B until 7 PM."
    candidate = "Do not fish in Stream B until 19:00. Do not swim in Stream A until 18:00."
    assert _decision(source, candidate) == "PASS"


def test_fhir_observation_subject_display_is_not_treated_as_verified_site_identity():
    import json
    from aquasignal.domain.context import assess_context_alignment, parse_oah_fhir_json

    resource = {
        "resourceType": "Observation",
        "status": "final",
        "subject": {"reference": "Location/stream-b", "display": "Stream A"},
        "code": {"text": "temperature"},
    }
    context = parse_oah_fhir_json(json.dumps(resource).encode("utf-8"))
    status, reason = assess_context_alignment(
        context, extractor.extract("Do not swim in Stream A until 18:00.")
    )
    assert status == "UNKNOWN"
    assert "derefer" in reason.casefold() or "display" in reason.casefold()
    assert context.raw_summary["subject_reference"] == "Location/stream-b"
    assert context.raw_summary["subject_display"] == "Stream A"


def test_fhir_location_resource_name_can_still_match_advisory_site():
    import json
    from aquasignal.domain.context import assess_context_alignment, parse_oah_fhir_json

    resource = {
        "resourceType": "Location",
        "id": "stream-a",
        "name": "Stream A",
        "status": "active",
    }
    context = parse_oah_fhir_json(json.dumps(resource).encode("utf-8"))
    status, _ = assess_context_alignment(
        context, extractor.extract("Do not swim in Stream A until 18:00.")
    )
    assert status == "MATCH"


def test_source_review_error_does_not_echo_full_advisory_contract():
    demo = client.get("/api/aqua/demo-context").json()
    source = "Do not kayak in Stream A until 18:00."
    response = client.post(
        "/api/aqua/authority",
        json={
            "source_text": source,
            "context": demo["context"],
            "context_token": demo["context_token"],
            "advisory_id": "privacy-review",
            "revision": 1,
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["state"] == "SOURCE_REVIEW"
    assert "source_contract" not in detail
    assert source not in response.text


def test_relational_context_does_not_match_broader_advisory_scope():
    from aquasignal.domain.context import AquaContext, AquaContextSource, assess_context_alignment

    context = AquaContext(
        source=AquaContextSource.RESILIENCE_COMPATIBLE_CSV,
        dataset_sha256="0" * 64,
        site="Stream A downstream of Bridge A",
        indicators=[],
        raw_summary={},
    )
    status, _ = assess_context_alignment(
        context, extractor.extract("Do not swim in Stream A until 18:00.")
    )
    assert status == "MISMATCH"


def test_relational_context_matches_same_relational_advisory_scope():
    from aquasignal.domain.context import AquaContext, AquaContextSource, assess_context_alignment

    context = AquaContext(
        source=AquaContextSource.RESILIENCE_COMPATIBLE_CSV,
        dataset_sha256="0" * 64,
        site="Stream A downstream of Bridge A",
        indicators=[],
        raw_summary={},
    )
    status, _ = assess_context_alignment(
        context,
        extractor.extract("Do not swim in Stream A downstream of Bridge A until 18:00."),
    )
    assert status == "MATCH"


def test_base_context_still_matches_narrower_supported_relational_advisory_scope():
    from aquasignal.domain.context import AquaContext, AquaContextSource, assess_context_alignment

    context = AquaContext(
        source=AquaContextSource.RESILIENCE_COMPATIBLE_CSV,
        dataset_sha256="0" * 64,
        site="Stream A",
        indicators=[],
        raw_summary={},
    )
    status, _ = assess_context_alignment(
        context,
        extractor.extract("Do not swim in Stream A downstream of Bridge A until 18:00."),
    )
    assert status == "MATCH"


def test_api_rejects_broader_advisory_than_relational_bound_context():
    csv_response = client.post(
        "/api/aqua/context/resilience-csv",
        json={
            "csv_text": "site,date\nStream A downstream of Bridge A,2026-10-04\n",
            "synthetic_demo": True,
        },
    )
    assert csv_response.status_code == 200, csv_response.text
    imported = csv_response.json()
    response = client.post(
        "/api/aqua/authority",
        json={
            "source_text": "Do not swim in Stream A until 18:00.",
            "context": imported["context"],
            "context_token": imported["context_token"],
            "advisory_id": "relational-scope",
            "revision": 1,
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["state"] == "SOURCE_REVIEW"
    assert detail["context_alignment"] == "MISMATCH"
