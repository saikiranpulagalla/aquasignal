from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from apps.aqua_api.main import app
from aquasignal.domain.context import parse_oah_fhir_json
from aquasignal.domain.freshwater import FreshwaterExtractor, assess_source_readiness
from aquasignal.integrity.verifier import AquaVerificationEngine


extractor = FreshwaterExtractor()
verifier = AquaVerificationEngine()
client = TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "candidate",
    [
        "Do not swim in Stream A\nuntil 18:00.",
        "Do not swim in Stream A\r\nuntil 18:00.",
        "Visitors\nmust avoid contact with Stream A until 18:00.",
        "Visitors must avoid\ncontact with Stream A until 18:00.",
        "Visitors must avoid contact with\nStream A until 18:00.",
        "Visitors must avoid contact with Stream A until\n18:00.",
    ],
)
def test_visual_line_wrap_does_not_change_supported_meaning(candidate: str):
    source = "Do not swim in Stream A until 18:00." if candidate.startswith("Do not") else "Visitors must avoid contact with Stream A until 18:00."
    source_contract = extractor.extract(source)
    candidate_contract = extractor.extract(candidate)
    assert assess_source_readiness(candidate_contract).ready
    assert verifier.verify(source_contract, candidate_contract).decision.value == "PASS"


def test_line_break_between_two_supported_directives_remains_a_directive_boundary():
    text = "Do not swim in Stream A until 18:00.\nDo not fish in Stream B until 19:00."
    contract = extractor.extract(text)
    assert assess_source_readiness(contract).ready
    assert len(contract.prohibited_actions) == 2
    assert {a.verb for a in contract.prohibited_actions} == {"swim", "fish"}


def test_line_wrapped_evidence_preserves_original_text_and_offsets():
    text = "Do not swim in Stream A\nuntil 18:00."
    contract = extractor.extract(text)
    assert len(contract.prohibited_actions) == 1
    evidence = contract.prohibited_actions[0].evidence
    assert evidence is not None
    assert evidence.quote == text
    assert text[evidence.start_char:evidence.end_char] == text


@pytest.mark.parametrize(
    "reference",
    [
        "Patient/123",
        "Encounter/456",
        "Practitioner/789",
        "RelatedPerson/42",
        "Person/99",
    ],
)
def test_environmental_observation_rejects_clinical_subject_reference(reference: str):
    resource = {
        "resourceType": "Observation",
        "subject": {"reference": reference, "display": "Not an environmental location"},
        "code": {"text": "temperature"},
    }
    with pytest.raises(ValueError, match="clinical|environmental Location"):
        parse_oah_fhir_json(json.dumps(resource).encode("utf-8"))


def test_environmental_observation_accepts_relative_location_subject_reference():
    resource = {
        "resourceType": "Observation",
        "subject": {"reference": "Location/stream-a", "display": "Stream A"},
        "code": {"text": "temperature"},
    }
    context = parse_oah_fhir_json(json.dumps(resource).encode("utf-8"))
    assert context.site == "Stream A"


def test_environmental_observation_accepts_absolute_location_subject_reference():
    resource = {
        "resourceType": "Observation",
        "subject": {
            "reference": "https://example.test/fhir/Location/stream-a",
            "display": "Stream A",
        },
        "code": {"text": "temperature"},
    }
    context = parse_oah_fhir_json(json.dumps(resource).encode("utf-8"))
    assert context.site == "Stream A"


@pytest.mark.parametrize(
    "clinical_fragment",
    [
        {"contained": [{"resourceType": "Patient", "id": "p1"}]},
        {"performer": [{"reference": "Practitioner/123"}]},
        {"extension": [{"url": "https://example.test/x", "valueReference": {"reference": "Patient/123"}}]},
    ],
)
def test_environmental_fhir_rejects_nested_clinical_resources_or_references(clinical_fragment: dict):
    resource = {
        "resourceType": "Observation",
        "subject": {"reference": "Location/stream-a", "display": "Stream A"},
        "code": {"text": "temperature"},
        **clinical_fragment,
    }
    with pytest.raises(ValueError, match="clinical"):
        parse_oah_fhir_json(json.dumps(resource).encode("utf-8"))


def test_api_fhir_privacy_failure_is_controlled_422_not_500():
    response = client.post(
        "/api/aqua/context/fhir",
        json={
            "resource": {
                "resourceType": "Observation",
                "subject": {"reference": "Patient/123", "display": "Alice"},
                "code": {"text": "temperature"},
            },
            "synthetic_demo": False,
        },
    )
    assert response.status_code == 422
    assert response.headers.get("cache-control") == "no-store"

@pytest.mark.parametrize(
    "date_value",
    [
        "0001-01-01T00:00:00+14:00",
        "9999-12-31T23:59:59-12:00",
    ],
)
def test_extreme_offset_csv_dates_fail_closed_without_overflow_500(date_value: str):
    csv_text = f"site,date,x\nStream A,{date_value},1\n"
    with pytest.raises(ValueError, match="representable UTC range"):
        from aquasignal.domain.context import parse_resilience_csv
        parse_resilience_csv(csv_text.encode("utf-8"))

    response = client.post(
        "/api/aqua/context/resilience-csv",
        json={"csv_text": csv_text, "synthetic_demo": False},
    )
    assert response.status_code == 422
    assert response.headers.get("cache-control") == "no-store"


def test_ordinary_offset_csv_dates_still_sort_chronologically():
    from aquasignal.domain.context import parse_resilience_csv
    context = parse_resilience_csv(
        b"site,date,x\n"
        b"Stream A,2026-10-01T23:00:00-02:00,1\n"
        b"Stream A,2026-10-02T02:00:00+02:00,2\n"
    )
    # 02:00+02:00 is 00:00Z and therefore precedes 23:00-02:00 (01:00Z).
    assert context.date_range == "2026-10-02T02:00:00+02:00 \u2026 2026-10-01T23:00:00-02:00"


def test_public_ui_guards_context_import_races_and_invalid_utf8_files():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[2] / "web_aqua" / "app.js").read_text(encoding="utf-8")
    assert "let contextGeneration=0" in js
    assert js.count("++contextGeneration") >= 3
    assert js.count("myContextGen!==contextGeneration") >= 3
    assert "new TextDecoder('utf-8',{fatal:true,ignoreBOM:true})" in js


def test_public_ui_handles_non_json_proxy_errors_without_json_parse_crash():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[2] / "web_aqua" / "app.js").read_text(encoding="utf-8")
    assert "await r.text()" in js
    assert "HTTP ${r.status}" in js


def test_direct_fhir_parser_rejects_duplicate_json_keys():
    raw = b'{"resourceType":"Location","id":"1","name":"Stream A","name":"Stream B"}'
    with pytest.raises(ValueError, match="duplicate JSON object key"):
        parse_oah_fhir_json(raw)


def test_raw_fhir_api_preserves_exact_pasted_json_hash_and_rejects_duplicates():
    import hashlib

    raw = '{"resourceType":"Location","id":"loc-1","name":"Stream A"}'
    response = client.post(
        "/api/aqua/context/fhir-raw",
        json={"json_text": raw, "synthetic_demo": False},
    )
    assert response.status_code == 200
    assert response.json()["context"]["dataset_sha256"] == hashlib.sha256(raw.encode("utf-8")).hexdigest()

    duplicate = '{"resourceType":"Location","id":"loc-1","name":"Stream A","name":"Stream B"}'
    response = client.post(
        "/api/aqua/context/fhir-raw",
        json={"json_text": duplicate, "synthetic_demo": False},
    )
    assert response.status_code == 422
    assert "duplicate JSON object key" in str(response.json()["detail"])


def test_public_ui_sends_raw_fhir_text_without_client_side_canonicalization():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[2] / "web_aqua" / "app.js").read_text(encoding="utf-8")
    assert "/api/aqua/context/fhir-raw" in js
    assert "json_text:raw" in js


def test_public_ui_surfaces_current_context_import_failures_without_stale_overwrite():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[2] / "web_aqua" / "app.js").read_text(encoding="utf-8")
    assert "alert(e.message||'CSV context import failed.')" in js
    assert "alert(e.message||'FHIR context import failed.')" in js
    assert js.count("if(myContextGen===contextGeneration)alert") >= 2

@pytest.mark.parametrize("status", ["banana", "FINAL", "", " Final "])
def test_fhir_observation_rejects_unknown_or_noncanonical_status_codes(status: str):
    resource = {
        "resourceType": "Observation",
        "status": status,
        "subject": {"reference": "Location/stream-a", "display": "Stream A"},
        "code": {"text": "temperature"},
    }
    with pytest.raises(ValueError, match="recognized FHIR R4 status code"):
        parse_oah_fhir_json(json.dumps(resource).encode("utf-8"))


@pytest.mark.parametrize(
    "status",
    ["registered", "preliminary", "final", "amended", "corrected", "cancelled", "entered-in-error", "unknown"],
)
def test_fhir_observation_accepts_r4_status_codes(status: str):
    resource = {
        "resourceType": "Observation",
        "status": status,
        "subject": {"reference": "Location/stream-a", "display": "Stream A"},
        "code": {"text": "temperature"},
    }
    context = parse_oah_fhir_json(json.dumps(resource).encode("utf-8"))
    assert context.raw_summary["status"] == status


@pytest.mark.parametrize("status", ["active", "suspended", "inactive"])
def test_fhir_location_accepts_r4_location_status_codes(status: str):
    resource = {"resourceType": "Location", "id": "stream-a", "name": "Stream A", "status": status}
    context = parse_oah_fhir_json(json.dumps(resource).encode("utf-8"))
    assert context.raw_summary["status"] == status


def test_fhir_location_rejects_observation_status_code():
    resource = {"resourceType": "Location", "id": "stream-a", "name": "Stream A", "status": "final"}
    with pytest.raises(ValueError, match="recognized FHIR R4 status code"):
        parse_oah_fhir_json(json.dumps(resource).encode("utf-8"))


def test_context_and_authority_tokens_are_not_cross_protocol_replayable():
    from aquasignal.domain.context import parse_resilience_csv
    from aquasignal.domain.freshwater import FreshwaterProfile
    from aquasignal.integrity.authority import (
        AquaAuthorityTokenError,
        AquaContextTokenError,
        AuthorityBinding,
        issue_aqua_authority_token,
        issue_context_token,
        verify_aqua_authority_token,
        verify_context_token,
    )

    secret = b"fifth-hunt-cross-protocol-secret-32bytes+"
    context = parse_resilience_csv(b"site,date,temp\nStream A,2026-10-04,20\n")
    source_text = "Visitors must avoid contact with Stream A until 18:00."
    contract = extractor.extract(source_text)
    binding = AuthorityBinding("cross-protocol", 1, FreshwaterProfile().profile_id)
    context_token = issue_context_token(secret, context=context)
    authority_token = issue_aqua_authority_token(
        secret,
        source_text=source_text,
        contract=contract,
        context=context,
        binding=binding,
    )

    with pytest.raises(AquaAuthorityTokenError, match="unsupported AquaSignal authority token"):
        verify_aqua_authority_token(
            secret,
            context_token,
            source_text=source_text,
            contract=contract,
            context=context,
            binding=binding,
        )
    with pytest.raises(AquaContextTokenError, match="unsupported AquaSignal context token"):
        verify_context_token(secret, authority_token, context=context)


def test_api_line_wrapped_authority_round_trips_to_single_line_candidate_pass():
    demo = client.get("/api/aqua/demo-context").json()
    source_text = "Visitors must avoid contact with Stream A\nuntil 18:00."
    authority = client.post(
        "/api/aqua/authority",
        json={
            "source_text": source_text,
            "context": demo["context"],
            "context_token": demo["context_token"],
            "advisory_id": "line-wrap-api",
            "revision": 1,
        },
    )
    assert authority.status_code == 200, authority.text
    body = authority.json()

    verified = client.post(
        "/api/aqua/verify",
        json={
            "source_text": source_text,
            "source_contract": body["source_contract"],
            "authority_token": body["authority_token"],
            "context": demo["context"],
            "advisory_id": "line-wrap-api",
            "revision": 1,
            "candidate_text": "Visitors must avoid contact with Stream A until 18:00.",
        },
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["decision"] == "PASS"

@pytest.mark.parametrize(
    "candidate",
    [
        "- Do not swim in Stream A until 18:00.",
        "* Do not swim in Stream A until 18:00.",
        "• Do not swim in Stream A until 18:00.",
        "1. Do not swim in Stream A until 18:00.",
        "1) Do not swim in Stream A until 18:00.",
    ],
)
def test_line_leading_list_decoration_is_semantically_neutral(candidate: str):
    source = "Do not swim in Stream A until 18:00."
    contract = extractor.extract(candidate)
    assert assess_source_readiness(contract).ready
    assert verifier.verify(extractor.extract(source), contract).decision.value == "PASS"
    evidence = contract.prohibited_actions[0].evidence
    assert evidence is not None
    assert evidence.quote == "Do not swim in Stream A until 18:00."
    assert candidate[evidence.start_char:evidence.end_char] == evidence.quote


def test_punctuated_multiline_bullet_list_parses_each_supported_directive_without_offset_drift():
    text = "- Do not swim in Stream A until 18:00.\n- Do not fish in Stream B until 19:00."
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


def test_extreme_json_nesting_is_controlled_before_framework_recursion_500():
    depth = 10_000
    body = (
        '{"resource":{"resourceType":"Location","id":"1","name":"Stream A","x":'
        + ("[" * depth) + "0" + ("]" * depth)
        + '},"synthetic_demo":false}'
    ).encode("utf-8")
    response = client.post(
        "/api/aqua/context/fhir",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert "nesting" in response.text.casefold()
    assert response.headers.get("cache-control") == "no-store"
    assert response.headers.get("content-security-policy")


def test_moderate_json_nesting_reaches_fhir_structure_guard_not_500():
    depth = 100
    body = (
        '{"resource":{"resourceType":"Location","id":"1","name":"Stream A","x":'
        + ("[" * depth) + "0" + ("]" * depth)
        + '},"synthetic_demo":false}'
    ).encode("utf-8")
    response = client.post(
        "/api/aqua/context/fhir",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert "nesting depth" in response.text.casefold()


def test_public_ui_does_not_let_stale_authority_failure_overwrite_newer_source_status():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[2] / "web_aqua" / "app.js").read_text(encoding="utf-8")
    assert "catch(e){if(key===sourceKey())" in js
