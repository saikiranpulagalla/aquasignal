from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from apps.aqua_api.main import MAX_REQUEST_BYTES, app
from aquasignal.domain.context import parse_oah_fhir_json, parse_resilience_csv


client = TestClient(app, raise_server_exceptions=False)


def _demo() -> dict:
    response = client.get("/api/aqua/demo-context")
    assert response.status_code == 200
    return response.json()


def _authority_payload() -> dict:
    demo = _demo()
    return {
        "source_text": "Visitors must avoid contact with Stream A until 18:00.",
        "context": demo["context"],
        "context_token": demo["context_token"],
        "advisory_id": "fourth-hunt-contract",
        "revision": 1,
    }


@pytest.mark.parametrize("revision", ["1", 1.0, True])
def test_authority_revision_is_strict_integer(revision):
    response = client.post("/api/aqua/authority", json={**_authority_payload(), "revision": revision})
    assert response.status_code == 422


@pytest.mark.parametrize("synthetic_demo", ["false", "true", 0, 1])
def test_context_synthetic_demo_is_strict_boolean(synthetic_demo):
    response = client.post(
        "/api/aqua/context/resilience-csv",
        json={
            "csv_text": "site,date,x\nStream A,2026-10-01,1\n",
            "synthetic_demo": synthetic_demo,
        },
    )
    assert response.status_code == 422


def test_duplicate_json_keys_are_rejected_instead_of_last_value_wins():
    raw = (
        '{"csv_text":"site,date,x\\nStream A,2026-10-01,1\\n",'
        '"synthetic_demo":false,"synthetic_demo":true}'
    )
    response = client.post(
        "/api/aqua/context/resilience-csv",
        content=raw,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Duplicate JSON object keys are not accepted"
    assert response.headers.get("cache-control") == "no-store"


def test_nested_duplicate_json_keys_are_rejected_too():
    raw = (
        '{"resource":{"resourceType":"Location","id":"1",'
        '"name":"Stream A","name":"Stream B"}}'
    )
    response = client.post(
        "/api/aqua/context/fhir",
        content=raw,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Duplicate JSON object keys are not accepted"


def test_actual_request_size_is_bounded_even_if_content_length_understates_body():
    payload = b'{"csv_text":"' + (b"A" * (MAX_REQUEST_BYTES + 1000)) + b'"}'
    response = client.post(
        "/api/aqua/context/resilience-csv",
        content=payload,
        headers={"content-type": "application/json", "content-length": "100"},
    )
    assert response.status_code == 413
    assert response.headers.get("cache-control") == "no-store"


def test_csv_alternate_metadata_aliases_do_not_become_indicators():
    context = parse_resilience_csv(
        b"site,location,date,time,latitude,longitude,temp\n"
        b"Stream A,Stream A,2026-10-01,18:00,1,2,22\n"
    )
    assert context.indicators == ["temp"]


def test_conflicting_site_alias_columns_are_rejected_as_ambiguous_provenance():
    with pytest.raises(ValueError, match="conflicting site/location metadata"):
        parse_resilience_csv(
            b"site,location,date,temp\n"
            b"Stream A,Stream B,2026-10-01,22\n"
        )


@pytest.mark.parametrize("status", [123, {}, [], True])
def test_recognized_fhir_status_field_has_strict_type(status):
    resource = {
        "resourceType": "Observation",
        "status": status,
        "subject": {"display": "Stream A"},
        "code": {"text": "temperature"},
    }
    with pytest.raises(ValueError, match="FHIR status must be a string"):
        parse_oah_fhir_json(json.dumps(resource).encode("utf-8"))


def test_fhir_status_is_not_silently_truncated():
    resource = {
        "resourceType": "Observation",
        "status": "x" * 81,
        "subject": {"display": "Stream A"},
        "code": {"text": "temperature"},
    }
    with pytest.raises(ValueError, match="FHIR status must be at most 80 characters"):
        parse_oah_fhir_json(json.dumps(resource).encode("utf-8"))


def _many_directives(prefix: str, count: int) -> str:
    return " ".join(
        f"Do not swim in Site {prefix}{i} until {i % 24:02d}:{(i * 7) % 60:02d}."
        for i in range(count)
    )


def test_source_contract_complexity_is_bounded_before_authority_minting():
    demo = _demo()
    response = client.post(
        "/api/aqua/authority",
        json={
            "source_text": _many_directives("S", 33),
            "context": demo["context"],
            "context_token": demo["context_token"],
            "advisory_id": "complex-source",
            "revision": 1,
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["state"] == "SOURCE_REVIEW"
    assert any("directive complexity" in reason for reason in detail["reasons"])


def test_candidate_contract_complexity_fails_closed_before_quadratic_verification():
    authority = client.post("/api/aqua/authority", json=_authority_payload())
    assert authority.status_code == 200
    frozen = authority.json()
    response = client.post(
        "/api/aqua/verify",
        json={
            "source_text": _authority_payload()["source_text"],
            "source_contract": frozen["source_contract"],
            "authority_token": frozen["authority_token"],
            "context": _authority_payload()["context"],
            "advisory_id": "fourth-hunt-contract",
            "revision": 1,
            "candidate_text": _many_directives("T", 33),
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["state"] == "REVIEW"
    assert "directive complexity" in detail["reason"]


def test_profile_directive_limit_still_allows_reasonable_multi_directive_advisory():
    demo = _demo()
    source = "Do not swim in Stream A until 18:00. " + _many_directives("S", 15)
    response = client.post(
        "/api/aqua/authority",
        json={
            "source_text": source,
            "context": demo["context"],
            "context_token": demo["context_token"],
            "advisory_id": "reasonable-complexity",
            "revision": 1,
        },
    )
    # The context is Stream A and the source names many other sites, so alignment is
    # UNKNOWN (mixed/partial), not an automatic mismatch; complexity itself is valid.
    assert response.status_code == 200


def test_invalid_runtime_size_limits_fail_fast_at_startup(tmp_path):
    import os
    import subprocess
    import sys

    root = __import__("pathlib").Path(__file__).resolve().parents[2]
    base_env = dict(os.environ)
    base_env["PYTHONPATH"] = str(root)
    probes = [
        ("AQUASIGNAL_MAX_ADVISORY_CHARS", "0"),
        ("AQUASIGNAL_MAX_ADVISORY_CHARS", "999999999"),
        ("AQUASIGNAL_MAX_REQUEST_BYTES", "not-an-int"),
        ("AQUASIGNAL_MAX_REQUEST_BYTES", "999999999"),
    ]
    for name, value in probes:
        env = dict(base_env)
        env[name] = value
        proc = subprocess.run(
            [sys.executable, "-c", "import apps.aqua_api.main"],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
        )
        assert proc.returncode != 0, (name, value, proc.stdout, proc.stderr)
        assert name in proc.stderr


def test_multi_directive_cross_binding_never_passes_even_when_global_facts_match():
    from aquasignal.domain.freshwater import FreshwaterExtractor, assess_source_readiness
    from aquasignal.integrity.verifier import AquaVerificationEngine

    extractor = FreshwaterExtractor()
    engine = AquaVerificationEngine()
    cases = [
        (
            "Do not swim in Stream A until 18:00. Do not fish in Stream B until 20:00.",
            "Do not swim in Stream B until 18:00. Do not fish in Stream A until 20:00.",
        ),
        (
            "Keep children away from Stream A until 18:00. Keep pets away from Stream B until 20:00.",
            "Keep children away from Stream B until 18:00. Keep pets away from Stream A until 20:00.",
        ),
        (
            "Visitors must avoid contact with Stream A until 18:00. Residents must avoid contact with Stream B until 20:00.",
            "Visitors must avoid contact with Stream B until 18:00. Residents must avoid contact with Stream A until 20:00.",
        ),
    ]
    for source, candidate in cases:
        source_contract = extractor.extract(source)
        assert assess_source_readiness(source_contract).ready
        result = engine.verify(source_contract, extractor.extract(candidate))
        assert result.decision.value != "PASS", (source, candidate, result.model_dump(mode="json"))


def test_duplicate_json_key_rejection_cannot_be_bypassed_by_omitting_content_type():
    raw = (
        '{"csv_text":"site,date,x\\nStream A,2026-10-01,1\\n",'
        '"synthetic_demo":false,"synthetic_demo":true}'
    )
    response = client.post("/api/aqua/context/resilience-csv", content=raw, headers={})
    assert response.status_code == 422
    assert response.json()["detail"] == "Duplicate JSON object keys are not accepted"


def test_duplicate_json_key_rejection_handles_utf8_bom_without_content_type():
    raw = ("\ufeff" + (
        '{"csv_text":"site,date,x\\nStream A,2026-10-01,1\\n",'
        '"synthetic_demo":false,"synthetic_demo":true}'
    )).encode("utf-8")
    response = client.post("/api/aqua/context/resilience-csv", content=raw, headers={})
    assert response.status_code == 422
    assert response.json()["detail"] == "Duplicate JSON object keys are not accepted"


@pytest.mark.parametrize("encoding", ["utf-16", "utf-32"])
def test_duplicate_json_key_rejection_handles_auto_detected_json_encodings_without_content_type(encoding):
    text = (
        '{"csv_text":"site,date,x\\nStream A,2026-10-01,1\\n",'
        '"synthetic_demo":false,"synthetic_demo":true}'
    )
    response = client.post(
        "/api/aqua/context/resilience-csv",
        content=text.encode(encoding),
        headers={},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Duplicate JSON object keys are not accepted"


def test_csv_site_alias_falls_back_to_populated_location_column():
    context = parse_resilience_csv(
        b"site,location,date,temp\n"
        b",Stream A,2026-10-01,22\n"
    )
    assert context.site == "Stream A"
    assert context.raw_summary["sites"] == ["Stream A"]


def test_csv_site_inventory_merges_consistent_aliases_across_blank_cells():
    context = parse_resilience_csv(
        b"site,location,date,temp\n"
        b"Stream A,Stream A,2026-10-01,22\n"
        b",Stream B,2026-10-02,21\n"
    )
    assert context.site is None
    assert context.raw_summary["sites"] == ["Stream A", "Stream B"]
    assert context.raw_summary["sites_complete"] is True


def test_csv_date_alias_falls_back_to_populated_lower_priority_column():
    context = parse_resilience_csv(
        b"datetime,date,site,temp\n"
        b",2026-10-01,Stream A,22\n"
    )
    assert context.date_range == "2026-10-01"
    assert context.raw_summary["date_field"] == "date"


def test_package_python_range_matches_frozen_release_runtime():
    import json
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    manifest = json.loads((root / "data/aqua/holdout_v15.manifest.json").read_text(encoding="utf-8"))
    assert manifest["python_version"] == "3.13.5"
    assert project["requires-python"] == "==3.13.5"


@pytest.mark.parametrize(
    ("source_site", "candidate_site"),
    [
        ("Site ①", "Site 1"),
        ("Site Ａ", "Site A"),
        ("River Ⅳ", "River IV"),
        ("Site ²", "Site 2"),
        ("Site ﬁ", "Site fi"),
    ],
)
def test_compatibility_unicode_cannot_collapse_distinct_freshwater_identifiers(source_site, candidate_site):
    from aquasignal.domain.freshwater import FreshwaterExtractor, assess_source_readiness
    from aquasignal.integrity.verifier import AquaVerificationEngine

    extractor = FreshwaterExtractor()
    source = extractor.extract(f"Visitors must avoid contact with {source_site} until 18:00.")
    candidate = extractor.extract(f"Visitors must avoid contact with {candidate_site} until 18:00.")
    assert assess_source_readiness(source).ready
    assert AquaVerificationEngine().verify(source, candidate).decision.value == "BLOCK"


@pytest.mark.parametrize(
    ("source_site", "candidate_site"),
    [
        ("River O’Neil", "River O'Neil"),
        ("Site C–1", "Site C-1"),
        ("River Cafe\u0301", "River Café"),
    ],
)
def test_explicit_typographic_and_canonical_unicode_site_equivalences_remain_clean(source_site, candidate_site):
    from aquasignal.domain.freshwater import FreshwaterExtractor, assess_source_readiness
    from aquasignal.integrity.verifier import AquaVerificationEngine

    extractor = FreshwaterExtractor()
    source = extractor.extract(f"Visitors must avoid contact with {source_site} until 18:00.")
    candidate = extractor.extract(f"Visitors must avoid contact with {candidate_site} until 18:00.")
    assert assess_source_readiness(source).ready
    assert AquaVerificationEngine().verify(source, candidate).decision.value == "PASS"

@pytest.mark.parametrize(
    ("context_site", "advisory_site", "expected"),
    [
        ("Site ①", "Site 1", "MISMATCH"),
        ("Site Ａ", "Site A", "MISMATCH"),
        ("River Ⅳ", "River IV", "MISMATCH"),
        ("Site ﬁ", "Site fi", "MISMATCH"),
        ("River O’Neil", "River O'Neil", "MATCH"),
        ("Site C–1", "Site C-1", "MATCH"),
        ("River Cafe\u0301", "River Café", "MATCH"),
    ],
)
def test_context_alignment_uses_conservative_identifier_unicode_identity(context_site, advisory_site, expected):
    from aquasignal.domain.context import AquaContext, AquaContextSource, assess_context_alignment
    from aquasignal.domain.freshwater import FreshwaterExtractor

    context = AquaContext(
        source=AquaContextSource.SYNTHETIC,
        dataset_sha256="a" * 64,
        site=context_site,
        synthetic_demo=True,
    )
    contract = FreshwaterExtractor().extract(
        f"Visitors must avoid contact with {advisory_site} until 18:00."
    )
    status, _ = assess_context_alignment(context, contract)
    assert status == expected


def test_csv_compatibility_distinct_site_ids_remain_multi_site_context():
    context = parse_resilience_csv(
        "site,date,temp\nSite ①,2026-10-01,22\nSite 1,2026-10-02,21\n".encode("utf-8")
    )
    assert context.site is None
    assert context.raw_summary["sites"] == ["Site ①", "Site 1"]
    assert context.raw_summary["sites_complete"] is True


def test_csv_canonically_equivalent_site_ids_deduplicate_cleanly():
    context = parse_resilience_csv(
        "site,date,temp\nRiver Cafe\u0301,2026-10-01,22\nRiver Café,2026-10-02,21\n".encode("utf-8")
    )
    assert context.site in {"River Cafe\u0301", "River Café"}
    assert len(context.raw_summary["sites"]) == 1


def test_unicode_symbol_case_mapping_cannot_collapse_operational_identifier():
    from aquasignal.domain.freshwater import FreshwaterExtractor, assess_source_readiness
    from aquasignal.integrity.verifier import AquaVerificationEngine

    extractor = FreshwaterExtractor()
    source = extractor.extract("Visitors must avoid contact with Site ϴ until 18:00.")
    candidate = extractor.extract("Visitors must avoid contact with Site Θ until 18:00.")
    assert assess_source_readiness(source).ready
    assert AquaVerificationEngine().verify(source, candidate).decision.value == "BLOCK"


def test_identifier_key_preserves_nfkc_only_compatibility_distinctions_for_bmp_word_characters():
    import re
    import unicodedata
    from aquasignal.domain.freshwater import aqua_identifier_text_key

    checked = 0
    for cp in range(0x00A0, 0x10000):
        ch = chr(cp)
        if not re.fullmatch(r"\w", ch, re.UNICODE):
            continue
        canonical = unicodedata.normalize("NFC", ch)
        compatibility = unicodedata.normalize("NFKC", ch)
        if compatibility == canonical or not compatibility:
            continue
        if not all(c.isprintable() and not c.isspace() for c in compatibility):
            continue
        checked += 1
        assert aqua_identifier_text_key(ch) != aqua_identifier_text_key(compatibility), (
            hex(cp), ch, compatibility, unicodedata.name(ch, "")
        )
    assert checked > 1000
