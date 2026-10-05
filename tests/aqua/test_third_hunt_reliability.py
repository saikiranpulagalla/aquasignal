from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from apps.aqua_api.main import app
from aquasignal.domain.context import (
    AquaContext,
    AquaContextSource,
    assess_context_alignment,
    parse_oah_fhir_json,
    parse_resilience_csv,
)
from aquasignal.domain.freshwater import FreshwaterExtractor, assess_source_readiness
from aquasignal.integrity.receipt import IntegrityReceipt, verify_integrity_receipt
from aquasignal.integrity.verifier import AquaVerificationEngine


extractor = FreshwaterExtractor()
verifier = AquaVerificationEngine()
client = TestClient(app, raise_server_exceptions=False)


def _decision(source: str, candidate: str) -> str:
    source_contract = extractor.extract(source)
    assert assess_source_readiness(source_contract).ready
    candidate_contract = extractor.extract(candidate)
    return verifier.verify(source_contract, candidate_contract).decision.value


def test_tiny_relative_quantity_change_does_not_pass_absolute_tolerance():
    assert _decision(
        "Boil the water for 0.000001 seconds before drinking.",
        "Boil the water for 0.0000001 seconds before drinking.",
    ) == "BLOCK"




def test_subpicosecond_relative_quantity_change_does_not_pass_absolute_floor():
    assert _decision(
        "Boil the water for 0.0000000000001 seconds before drinking.",
        "Boil the water for 0.0000000000009 seconds before drinking.",
    ) == "BLOCK"


def test_large_integer_quantity_precision_collision_is_detected():
    assert _decision(
        "Boil the water for 9007199254740992 seconds before drinking.",
        "Boil the water for 9007199254740993 seconds before drinking.",
    ) == "BLOCK"


def test_nonfinite_quantity_cannot_become_source_ready():
    huge = "9" * 400
    contract = extractor.extract(f"Boil the water for {huge} hours before drinking.")
    readiness = assess_source_readiness(contract)
    assert readiness.ready is False
    assert not contract.quantities
    assert contract.unresolved_operational_text




def test_nonfinite_candidate_quantity_fails_closed_without_server_error():
    demo = client.get("/api/aqua/demo-context").json()
    source = "Boil the water for 1 minute before drinking."
    authority = client.post(
        "/api/aqua/authority",
        json={
            "source_text": source,
            "context": demo["context"],
            "context_token": demo["context_token"],
            "advisory_id": "nonfinite-candidate",
            "revision": 1,
        },
    )
    # The demo context is Stream A and boil guidance has no named site, so alignment is UNKNOWN but source is still valid.
    assert authority.status_code == 200
    auth = authority.json()
    huge = "9" * 400
    response = client.post(
        "/api/aqua/verify",
        json={
            "source_text": source,
            "source_contract": auth["source_contract"],
            "authority_token": auth["authority_token"],
            "context": demo["context"],
            "advisory_id": "nonfinite-candidate",
            "revision": 1,
            "candidate_text": f"Boil the water for {huge} hours before drinking.",
        },
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "REVIEW"


def test_internal_period_in_supported_site_identifier_is_semantically_significant():
    assert _decision(
        "Visitors must avoid contact with Site A.B until 18:00.",
        "Visitors must avoid contact with Site A B until 18:00.",
    ) == "BLOCK"


@pytest.mark.parametrize(
    ("context_site", "source_site"),
    [
        ("River O’Neil", "River O’Neil"),
        ("Site C–1", "Site C–1"),
    ],
)
def test_context_alignment_normalizes_supported_typographic_identifier_punctuation(context_site: str, source_site: str):
    context = AquaContext(
        source=AquaContextSource.SYNTHETIC,
        dataset_sha256="a" * 64,
        site=context_site,
        synthetic_demo=True,
    )
    contract = extractor.extract(f"Visitors must avoid contact with {source_site} until 18:00.")
    assert assess_source_readiness(contract).ready
    status, _ = assess_context_alignment(context, contract)
    assert status == "MATCH"


def test_multi_site_csv_alignment_matches_member_and_rejects_known_nonmember():
    context = parse_resilience_csv(
        b"site,date,indicator\nStream A,2026-10-01,x\nStream B,2026-10-02,y\n"
    )
    assert context.site is None
    member = extractor.extract("Visitors must avoid contact with Stream B until 18:00.")
    missing = extractor.extract("Visitors must avoid contact with Stream Z until 18:00.")
    assert assess_context_alignment(context, member)[0] == "MATCH"
    assert assess_context_alignment(context, missing)[0] == "MISMATCH"


def test_api_rejects_bidi_and_zero_width_controls_in_advisory_text():
    demo = client.get("/api/aqua/demo-context").json()
    for bad in [
        "Visitors must avoid contact with Stream A\u202e until 18:00.",
        "Visitors must avoid contact with Stream A\u200b until 18:00.",
    ]:
        response = client.post(
            "/api/aqua/authority",
            json={
                "source_text": bad,
                "context": demo["context"],
                "context_token": demo["context_token"],
                "advisory_id": "unicode-control",
                "revision": 1,
            },
        )
        assert response.status_code == 422
        assert "control" in response.text.casefold() or "format" in response.text.casefold()


def test_context_import_rejects_invisible_control_characters_in_site_metadata():
    with pytest.raises(ValueError):
        parse_resilience_csv("site,date,indicator\nStream A\u202e,2026-10-01,x\n".encode("utf-8"))
    with pytest.raises(ValueError):
        parse_oah_fhir_json(
            b'{"resourceType":"Location","id":"loc-1","name":"Stream A\\u202e"}'
        )


def test_dynamic_aqua_api_responses_are_not_cacheable():
    response = client.get("/api/aqua/demo-context")
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    response = client.get("/api/aqua/release-evidence")
    assert response.status_code in {200, 503}
    assert response.headers.get("cache-control") == "no-store"


def test_review_receipt_preserves_structured_unknown_signal_reason():
    demo = client.get("/api/aqua/demo-context").json()
    source = "Visitors must avoid contact with Stream A until 18:00."
    authority = client.post(
        "/api/aqua/authority",
        json={
            "source_text": source,
            "context": demo["context"],
            "context_token": demo["context_token"],
            "advisory_id": "review-receipt",
            "revision": 1,
        },
    )
    assert authority.status_code == 200
    auth = authority.json()
    verified = client.post(
        "/api/aqua/verify",
        json={
            "source_text": source,
            "source_contract": auth["source_contract"],
            "authority_token": auth["authority_token"],
            "context": demo["context"],
            "advisory_id": "review-receipt",
            "revision": 1,
            "candidate_text": "Visitors must keep away from Stream A until 18:00.",
        },
    )
    assert verified.status_code == 200
    body = verified.json()
    assert body["decision"] == "REVIEW"
    receipt = body["integrity_receipt"]
    assert any(item.get("status") == "UNKNOWN" for item in receipt["differences"])
    model = IntegrityReceipt.model_validate(receipt)
    from apps.aqua_api.main import _AUTHORITY_SECRET
    assert verify_integrity_receipt(_AUTHORITY_SECRET, model)


def test_stateless_verification_remains_correct_under_parallel_requests():
    demo = client.get("/api/aqua/demo-context").json()

    def flow(i: int) -> tuple[int, str]:
        source = "Visitors must avoid contact with Stream A until 18:00."
        authority = client.post(
            "/api/aqua/authority",
            json={
                "source_text": source,
                "context": demo["context"],
                "context_token": demo["context_token"],
                "advisory_id": f"parallel-{i}",
                "revision": 1,
            },
        )
        if authority.status_code != 200:
            return authority.status_code, "AUTH"
        auth = authority.json()
        verified = client.post(
            "/api/aqua/verify",
            json={
                "source_text": source,
                "source_contract": auth["source_contract"],
                "authority_token": auth["authority_token"],
                "context": demo["context"],
                "advisory_id": f"parallel-{i}",
                "revision": 1,
                "candidate_text": source,
            },
        )
        return verified.status_code, verified.json().get("decision") if verified.status_code == 200 else "VERIFY"

    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = list(pool.map(flow, range(36)))
    assert outcomes == [(200, "PASS")] * 36


def test_third_hunt_metamorphic_supported_grammar_matrix():
    clean_pairs: list[tuple[str, str]] = []
    unsafe_pairs: list[tuple[str, str]] = []
    for place in ["Stream A", "River Aster", "Site C1", "Zone 7"]:
        clean_pairs.extend([
            (f"Visitors must avoid contact with {place} until midnight.", f"Visitors must avoid contact with {place} until 00:00."),
            (f"Visitors must avoid contact with {place} until noon.", f"Visitors must avoid contact with {place} until 12:00."),
            (f"Visitors must avoid contact with {place} until 6 PM.", f"Visitors must avoid contact with {place} until 18:00."),
            (f"Don't swim in {place} until 18:00.", f"Do not swim in {place} until 18:00."),
        ])
        unsafe_pairs.extend([
            (f"Visitors must avoid contact with {place} until 18:00.", f"Visitors may avoid contact with {place} until 18:00."),
            (f"Visitors must avoid contact with {place} until 18:00.", f"Visitors can avoid contact with {place} until 18:00."),
            (f"Visitors must avoid contact with {place} until 18:00.", f"Visitors should avoid contact with {place} until 18:00."),
            (f"Do not swim in {place} until 18:00.", f"Swim in {place} until 18:00."),
        ])

    clean_pairs.extend([
        ("Boil the water for 60 seconds before drinking.", "Boil the water for 1 minute before drinking."),
        ("Boil the water for 1 hour before drinking.", "Boil the water for 60 minutes before drinking."),
        ("Boil the water for 0.1 hours before drinking.", "Boil the water for 6 minutes before drinking."),
        ("Keep children and pets away from Stream A until 18:00.", "Keep pets and children away from Stream A until 18:00."),
    ])
    unsafe_pairs.extend([
        ("Boil the water for at least 60 seconds before drinking.", "Boil the water for 1 minute before drinking."),
        ("Boil the water for 0.000001 seconds before drinking.", "Boil the water for 0.0000001 seconds before drinking."),
        ("Visitors must avoid contact with Site A.B until 18:00.", "Visitors must avoid contact with Site A B until 18:00."),
        ("Keep children and pets away from Stream A until 18:00.", "Keep children away from Stream A until 18:00."),
    ])

    for source, candidate in clean_pairs:
        assert _decision(source, candidate) == "PASS", (source, candidate)
    for source, candidate in unsafe_pairs:
        assert _decision(source, candidate) == "BLOCK", (source, candidate)


def test_truncated_multi_site_inventory_never_asserts_false_mismatch():
    rows = ["site,date,indicator"] + [
        f"Stream {i},2026-10-{(i % 28) + 1:02d},x" for i in range(1, 31)
    ]
    context = parse_resilience_csv(("\n".join(rows) + "\n").encode())
    assert context.raw_summary["sites_complete"] is False
    known = extractor.extract("Visitors must avoid contact with Stream 2 until 18:00.")
    not_in_sample = extractor.extract("Visitors must avoid contact with Stream 29 until 18:00.")
    assert assess_context_alignment(context, known)[0] == "MATCH"
    assert assess_context_alignment(context, not_in_sample)[0] == "UNKNOWN"


def test_api_rejects_spoofable_or_blank_advisory_identifiers():
    from fastapi.testclient import TestClient
    from apps.aqua_api.main import app

    client = TestClient(app)
    demo = client.get('/api/aqua/demo-context').json()
    base = {
        'source_text': 'Visitors must avoid contact with Stream A until 18:00.',
        'context': demo['context'],
        'context_token': demo['context_token'],
        'revision': 1,
    }
    for advisory_id in ('   ', 'adv\u202eevil', 'adv\u200bevil'):
        response = client.post('/api/aqua/authority', json={**base, 'advisory_id': advisory_id})
        assert response.status_code == 422


def test_advisory_identifier_whitespace_is_canonicalized_across_authority_and_verify():
    from fastapi.testclient import TestClient
    from apps.aqua_api.main import app

    client = TestClient(app)
    demo = client.get('/api/aqua/demo-context').json()
    source = 'Visitors must avoid contact with Stream A until 18:00.'
    authority = client.post('/api/aqua/authority', json={
        'source_text': source,
        'context': demo['context'],
        'context_token': demo['context_token'],
        'advisory_id': '  canonical-id  ',
        'revision': 1,
    })
    assert authority.status_code == 200
    frozen = authority.json()
    verified = client.post('/api/aqua/verify', json={
        'source_text': source,
        'source_contract': frozen['source_contract'],
        'authority_token': frozen['authority_token'],
        'context': demo['context'],
        'advisory_id': 'canonical-id',
        'revision': 1,
        'candidate_text': source,
    })
    assert verified.status_code == 200
    body = verified.json()
    assert body['decision'] == 'PASS'
    assert body['integrity_receipt']['advisory_id'] == 'canonical-id'


def test_public_ui_preflights_large_context_files_and_defers_receipt_url_revocation():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[2] / 'web_aqua' / 'app.js').read_text(encoding='utf-8')
    assert 'file.size>2000000' in js
    assert "new TextEncoder().encode(raw).length>1000000" in js
    assert 'setTimeout(()=>URL.revokeObjectURL(url),0)' in js


def test_distinct_tiny_duplicate_boiling_constraints_are_not_deduplicated_away():
    from aquasignal.domain.freshwater import FreshwaterExtractor, assess_source_readiness
    from aquasignal.integrity.verifier import AquaVerificationEngine
    extractor = FreshwaterExtractor()
    source = extractor.extract(
        'Boil the water for 0.0000000000001 seconds before drinking. '
        'Boil the water for 0.0000000000002 seconds before drinking.'
    )
    candidate = extractor.extract('Boil the water for 0.0000000000001 seconds before drinking.')
    readiness = assess_source_readiness(source)
    assert readiness.ready is False
    assert any('conflicting constraints' in reason for reason in readiness.reasons)
    assert len(source.required_actions) == 2
    assert len(source.quantities) == 2
    # The source cannot be frozen as authoritative, so dropping one distinct
    # constraint can never obtain an automatic PASS in the API workflow.


def test_semantically_identical_duplicate_durations_can_still_collapse_safely():
    from aquasignal.domain.freshwater import FreshwaterExtractor, assess_source_readiness
    from aquasignal.integrity.verifier import AquaVerificationEngine
    extractor = FreshwaterExtractor()
    source = extractor.extract(
        'Boil the water for 1 minute before drinking. '
        'Boil the water for 60 seconds before drinking.'
    )
    candidate = extractor.extract('Boil the water for 60 seconds before drinking.')
    assert assess_source_readiness(source).ready
    assert len(source.required_actions) == 1
    assert len(source.quantities) == 1
    assert AquaVerificationEngine().verify(source, candidate).decision.value == 'PASS'

@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/aqua/context/resilience-csv", {"csv_text": "site,date,x\\nStream A,2026-10-01,1\\n", "unexpected": "ignored?"}),
        ("/api/aqua/context/fhir", {"resource": {"resourceType": "Location", "id": "1", "name": "Stream A"}, "unexpected": "ignored?"}),
    ],
)
def test_public_request_models_reject_unknown_top_level_fields(path: str, payload: dict):
    response = client.post(path, json=payload)
    assert response.status_code == 422
    assert "extra_forbidden" in response.text


def test_authority_and_verify_reject_unknown_top_level_fields():
    demo = client.get("/api/aqua/demo-context").json()
    authority_payload = {
        "source_text": "Visitors must avoid contact with Stream A until 18:00.",
        "context": demo["context"],
        "context_token": demo["context_token"],
        "advisory_id": "strict-schema",
        "revision": 1,
    }
    rejected = client.post("/api/aqua/authority", json={**authority_payload, "rev": 2})
    assert rejected.status_code == 422
    authority = client.post("/api/aqua/authority", json=authority_payload)
    assert authority.status_code == 200
    frozen = authority.json()
    verify_payload = {
        "source_text": authority_payload["source_text"],
        "source_contract": frozen["source_contract"],
        "authority_token": frozen["authority_token"],
        "context": demo["context"],
        "advisory_id": "strict-schema",
        "revision": 1,
        "candidate_text": authority_payload["source_text"],
    }
    rejected = client.post("/api/aqua/verify", json={**verify_payload, "candidate": "typo"})
    assert rejected.status_code == 422


def test_fhir_import_rejects_excessive_irrelevant_nesting_without_500():
    resource = {"resourceType": "Location", "id": "loc-1", "name": "Stream A"}
    cursor = resource
    for _ in range(40):
        cursor["unused"] = {}
        cursor = cursor["unused"]
    response = client.post("/api/aqua/context/fhir", json={"resource": resource})
    assert response.status_code == 422
    assert "nesting depth" in response.text



def test_csv_date_field_selection_is_semantic_not_header_order_dependent():
    first_time = parse_resilience_csv(
        b"time,date,site,indicator\n18:00,2026-10-01,Stream A,x\n"
    )
    first_date = parse_resilience_csv(
        b"date,time,site,indicator\n2026-10-01,18:00,Stream A,x\n"
    )
    assert first_time.date_range == "2026-10-01"
    assert first_date.date_range == "2026-10-01"
    assert first_time.raw_summary["date_field"] == "date"
    assert first_date.raw_summary["date_field"] == "date"


def test_resource_resolution_does_not_mistake_unrelated_data_or_web_directories_for_source_tree(tmp_path):
    from apps.aqua_api.main import _resolve_resource_root
    from aquasignal.evaluation.evidence import _is_source_tree

    fake_install = tmp_path / "site-packages"
    (fake_install / "data").mkdir(parents=True)
    (fake_install / "web_aqua").mkdir()
    (fake_install / "web_aqua" / "index.html").write_text("wrong", encoding="utf-8")
    assert _is_source_tree(fake_install) is False
    assert _resolve_resource_root(fake_install) == fake_install / "aquasignal" / "resources"

    source = tmp_path / "source"
    (source / "data" / "aqua").mkdir(parents=True)
    (source / "web_aqua").mkdir()
    (source / "web_aqua" / "index.html").write_text("ok", encoding="utf-8")
    (source / "pyproject.toml").write_text("[project]", encoding="utf-8")
    assert _is_source_tree(source) is True
    assert _resolve_resource_root(source) == source


def test_malformed_surrogate_validation_never_becomes_500_or_echoes_raw_input():
    raw_csv = b'{"csv_text":"site,date,x\\nStream \\ud800,2026-10-01,1\\n"}'
    response = client.post(
        "/api/aqua/context/resilience-csv",
        content=raw_csv,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert "string_unicode" in response.text
    assert "\\ud800" not in response.text

    demo = client.get("/api/aqua/demo-context").json()
    raw_authority = (
        '{"source_text":"Visitors \\ud800 must avoid contact with Stream A until 18:00.",'
        '"context":' + __import__("json").dumps(demo["context"]) + ','
        '"context_token":' + __import__("json").dumps(demo["context_token"]) + ','
        '"advisory_id":"surrogate","revision":1}'
    ).encode("ascii")
    response = client.post(
        "/api/aqua/authority",
        content=raw_authority,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert "string_unicode" in response.text
    assert "\\ud800" not in response.text

@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_fhir_import_rejects_nonfinite_json_numbers(literal: str):
    raw = (
        '{"resource":{"resourceType":"Location","id":"1","name":"Stream A",'
        '"extension":[{"valueDecimal":' + literal + '}]}}'
    ).encode("ascii")
    response = client.post(
        "/api/aqua/context/fhir",
        content=raw,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert "NaN or Infinity" in response.text


def test_deep_forged_context_is_rejected_before_token_hashing_can_crash():
    import json

    demo = client.get("/api/aqua/demo-context").json()
    context = dict(demo["context"])
    nested: dict = {}
    cursor = nested
    for _ in range(40):
        cursor["x"] = {}
        cursor = cursor["x"]
    context["raw_summary"] = nested
    response = client.post(
        "/api/aqua/authority",
        content=json.dumps({
            "source_text": "Visitors must avoid contact with Stream A until 18:00.",
            "context": context,
            "context_token": demo["context_token"],
            "advisory_id": "deep-forgery",
            "revision": 1,
        }),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert "nesting depth" in response.text


def test_readiness_distinguishes_liveness_from_release_qualification():
    health = client.get("/api/aqua/health")
    assert health.status_code == 200
    ready = client.get("/api/aqua/ready")
    # During a hardening cycle the previous frozen evidence is intentionally stale;
    # final release gating must turn this into 200 only after a fresh holdout is sealed.
    assert ready.status_code in {200, 503}
    if ready.status_code == 200:
        assert ready.json()["release_evidence_verified"] is True
    else:
        assert ready.json()["detail"]["state"] == "NOT_READY"


def test_chunked_body_without_content_length_is_bounded_before_validation():
    from apps.aqua_api.main import MAX_REQUEST_BYTES

    def body_chunks():
        yield b'{"csv_text":"'
        remaining = MAX_REQUEST_BYTES + 50_000
        chunk = b"A" * 65_536
        while remaining > 0:
            part = chunk[: min(len(chunk), remaining)]
            remaining -= len(part)
            yield part
        yield b'"}'

    response = client.post(
        "/api/aqua/context/resilience-csv",
        content=body_chunks(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["detail"] == "Request body exceeds AquaSignal prototype limit"
    assert response.headers.get("content-security-policy")
    assert response.headers.get("cache-control") == "no-store"

@pytest.mark.parametrize("abbr", ["St.", "Mt."])
def test_named_waterbody_abbreviation_period_does_not_split_sentence(abbr: str):
    source = f"Visitors must avoid contact with River {abbr} John until 18:00."
    candidate = f"Visitors must avoid contact with River {abbr} John until 18:00."
    contract = extractor.extract(source)
    assert assess_source_readiness(contract).ready, contract.unresolved_operational_text
    assert _decision(source, candidate) == "PASS"


def test_abbreviation_fix_does_not_merge_real_sentence_boundary_after_site_identifier():
    source = "Visitors must avoid contact with Site A. Keep children away from Site A until 18:00."
    contract = extractor.extract(source)
    assert assess_source_readiness(contract).ready, contract.unresolved_operational_text
    assert len(contract.prohibited_actions) == 1
    assert len(contract.required_actions) == 1


def test_supported_grammar_metamorphic_identity_and_single_slot_mutations_are_regression_gated():
    places = ["Stream A", "River North", "Site C-1", "downstream of Bridge A"]
    times = ["18:00", "6 PM", "07:30"]
    sources = []
    for place in places:
        for time in times:
            sources.extend([
                f"Visitors must avoid contact with {place} until {time}.",
                f"Do not swim in {place} until {time}.",
                f"Keep children and pets away from {place} until {time}.",
            ])
    # Identity is a powerful metamorphic invariant: every declared-profile sentence
    # must be source-ready and preserve itself.
    for text in sources:
        assert _decision(text, text) == "PASS", text

    mutations = [
        (
            "Visitors must avoid contact with Stream A after 18:00.",
            "Visitors must avoid contact with Stream A before 18:00.",
        ),
        (
            "Visitors must avoid contact with Stream A until 18:00.",
            "Visitors should avoid contact with Stream A until 18:00.",
        ),
        (
            "Keep children and pets away from Stream A until 18:00.",
            "Keep children away from Stream A until 18:00.",
        ),
        (
            "Do not swim in Stream A until 18:00.",
            "Do not swim in Stream B until 18:00.",
        ),
        (
            "Do not swim or fish in Stream A until 18:00.",
            "Do not swim in Stream A until 18:00.",
        ),
        (
            "Boil the water for 1 minute before drinking.",
            "Boil the water for 30 seconds before drinking.",
        ),
    ]
    for source, candidate in mutations:
        assert _decision(source, candidate) != "PASS", (source, candidate)
