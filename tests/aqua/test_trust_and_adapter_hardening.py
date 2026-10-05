from pathlib import Path
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from apps.aqua_api.main import app
from aquasignal.domain.context import parse_oah_fhir_json, parse_resilience_csv


client = TestClient(app)


def test_csv_does_not_treat_area_notes_as_site_column():
    data = b"site,area_notes,date,indicator\nStream A,Stream B should be visited,2026-10-03,x\n"
    context = parse_resilience_csv(data)
    assert context.site == "Stream A"


def test_csv_dates_are_chronologically_sorted():
    data = b"site,date,indicator\nStream A,2026-10-03,x\nStream A,2026-10-01,y\nStream A,2026-10-02,z\n"
    context = parse_resilience_csv(data)
    assert context.date_range == "2026-10-01 … 2026-10-03"


def test_csv_site_values_dedupe_case_and_whitespace():
    data = b"site,date,indicator\nStream A,2026-10-01,x\n stream   a ,2026-10-02,y\n"
    context = parse_resilience_csv(data)
    assert context.site == "Stream A"
    assert len(context.raw_summary["sites"]) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"resourceType": "Observation", "subject": "Location/1"},
        {"resourceType": "Observation", "meta": "bad", "subject": {"display": "Stream A"}},
        {"resourceType": "Observation", "code": [], "subject": {"display": "Stream A"}},
    ],
)
def test_malformed_fhir_shapes_return_value_error_not_attribute_error(payload):
    with pytest.raises(ValueError):
        parse_oah_fhir_json(json.dumps(payload).encode())


def test_fhir_preserves_all_declared_profiles_for_exact_policy_checking():
    payload = {
        "resourceType": "Observation",
        "meta": {"profile": ["https://example.test/generic", "https://example.test/oah-second"]},
        "subject": {"display": "Stream A"},
        "code": {"text": "Indicator"},
    }
    context = parse_oah_fhir_json(json.dumps(payload).encode())
    assert context.raw_summary["profiles"] == payload["meta"]["profile"]


def test_context_import_mints_token_and_authority_requires_it():
    imported = client.post(
        "/api/aqua/context/resilience-csv",
        json={"csv_text": "site,date,indicator\nStream A,2026-10-01,x\n", "synthetic_demo": False},
    )
    assert imported.status_code == 200
    body = imported.json()
    assert body["context_token"]

    req = {
        "source_text": "Visitors must avoid contact with Stream A until 18:00.",
        "context": body["context"],
        "advisory_id": "adv",
        "revision": 1,
    }
    missing = client.post("/api/aqua/authority", json=req)
    assert missing.status_code == 422

    req["context_token"] = body["context_token"]
    ok = client.post("/api/aqua/authority", json=req)
    assert ok.status_code == 200


def test_handcrafted_context_cannot_be_signed_without_import_token():
    imported = client.get("/api/aqua/demo-context").json()
    forged = deepcopy(imported["context"])
    forged["dataset_sha256"] = "0" * 64
    forged["indicators"] = ["FORGED"]
    response = client.post(
        "/api/aqua/authority",
        json={
            "source_text": "Visitors must avoid contact with Stream A until 18:00.",
            "context": forged,
            "context_token": imported["context_token"],
            "advisory_id": "adv",
            "revision": 1,
        },
    )
    assert response.status_code == 409


def test_authority_token_stays_compact_for_repeated_valid_directives():
    demo = client.get("/api/aqua/demo-context").json()
    source = " ".join(["Visitors must avoid contact with Stream A until 18:00."] * 50)
    response = client.post(
        "/api/aqua/authority",
        json={
            "source_text": source,
            "context": demo["context"],
            "context_token": demo["context_token"],
            "advisory_id": "long",
            "revision": 1,
        },
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["authority_token"]) < 5000


def test_receipt_is_signed_and_context_changes_verification_identity():
    demo = client.get("/api/aqua/demo-context").json()
    authority = client.post(
        "/api/aqua/authority",
        json={
            "source_text": "Visitors must avoid contact with Stream A until 18:00.",
            "context": demo["context"],
            "context_token": demo["context_token"],
            "advisory_id": "adv",
            "revision": 1,
        },
    ).json()
    response = client.post(
        "/api/aqua/verify",
        json={
            "source_text": "Visitors must avoid contact with Stream A until 18:00.",
            "source_contract": authority["source_contract"],
            "authority_token": authority["authority_token"],
            "context": demo["context"],
            "advisory_id": "adv",
            "revision": 1,
            "candidate_text": "Visitors must avoid contact with Stream A until 18:00.",
        },
    )
    assert response.status_code == 200
    receipt = response.json()["integrity_receipt"]
    assert receipt["signature"]
    assert receipt["verification_id"].startswith("AQ-")


def test_csv_mixed_timezone_date_shapes_do_not_crash_sorting():
    data = b"site,date,indicator\nStream A,2026-10-03T00:00:00Z,x\nStream A,2026-10-01,y\n"
    context = parse_resilience_csv(data)
    assert context.date_range.startswith("2026-10-01")


def test_integrity_receipt_signature_is_self_verifiable():
    from aquasignal.integrity.receipt import make_integrity_receipt, verify_integrity_receipt
    from aquasignal.domain.context import AquaContext, AquaContextSource
    from aquasignal.integrity.verifier import AquaVerificationEngine
    from aquasignal.domain.freshwater import FreshwaterExtractor
    text = "Avoid direct contact with Stream A until 18:00."
    contract = FreshwaterExtractor().extract(text)
    result = AquaVerificationEngine().verify(contract, contract)
    context = AquaContext(source=AquaContextSource.SYNTHETIC, dataset_sha256="a"*64, site="Stream A", synthetic_demo=True)
    receipt = make_integrity_receipt(secret=b"secret", source_text=text, candidate_text=text, context=context, advisory_id="a", revision=1, profile_id=FreshwaterExtractor.profile.profile_id, result=result)
    assert verify_integrity_receipt(b"secret", receipt)


def test_csv_rejects_ambiguous_duplicate_headers():
    data = b"site,Site,date,indicator\nStream A,Stream A,2026-10-01,x\n"
    with pytest.raises(ValueError):
        parse_resilience_csv(data)


def test_csv_rejects_excessively_long_header():
    header = "x" * 251
    data = f"site,date,{header}\nStream A,2026-10-01,1\n".encode()
    with pytest.raises(ValueError):
        parse_resilience_csv(data)


def test_csv_rejects_rows_with_extra_unheaded_fields():
    data = b"site,date,indicator\nStream A,2026-10-01,x,unexpected\n"
    with pytest.raises(ValueError):
        parse_resilience_csv(data)


def test_fhir_rejects_overlong_profile_and_indicator_text():
    too_long_profile = {
        "resourceType": "Observation",
        "meta": {"profile": ["x" * 501]},
        "subject": {"display": "Stream A"},
        "code": {"text": "Indicator"},
    }
    with pytest.raises(ValueError):
        parse_oah_fhir_json(json.dumps(too_long_profile).encode())

    too_long_indicator = {
        "resourceType": "Observation",
        "subject": {"display": "Stream A"},
        "code": {"text": "x" * 201},
    }
    with pytest.raises(ValueError):
        parse_oah_fhir_json(json.dumps(too_long_indicator).encode())


def test_receipt_verification_endpoint_detects_tampering():
    demo = client.get("/api/aqua/demo-context").json()
    authority = client.post(
        "/api/aqua/authority",
        json={
            "source_text": "Visitors must avoid contact with Stream A until 18:00.",
            "context": demo["context"],
            "context_token": demo["context_token"],
            "advisory_id": "receipt-demo",
            "revision": 1,
        },
    ).json()
    verified = client.post(
        "/api/aqua/verify",
        json={
            "source_text": "Visitors must avoid contact with Stream A until 18:00.",
            "source_contract": authority["source_contract"],
            "authority_token": authority["authority_token"],
            "context": demo["context"],
            "advisory_id": "receipt-demo",
            "revision": 1,
            "candidate_text": "Visitors must avoid contact with Stream A until 18:00.",
        },
    ).json()
    receipt = verified["integrity_receipt"]
    check = client.post("/api/aqua/receipt/verify", json=receipt)
    assert check.status_code == 200
    assert check.json()["valid"] is True

    tampered = deepcopy(receipt)
    tampered["decision"] = "BLOCK"
    check = client.post("/api/aqua/receipt/verify", json=tampered)
    assert check.status_code == 200
    assert check.json()["valid"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {"resourceType": "Observation", "meta": []},
        {"resourceType": "Observation", "subject": []},
        {"resourceType": "Observation", "code": {"coding": {}}},
        {"resourceType": "Observation", "meta": {"profile": ""}},
    ],
)
def test_falsey_but_wrong_fhir_shapes_are_not_silently_defaulted(payload):
    with pytest.raises(ValueError):
        parse_oah_fhir_json(json.dumps(payload).encode())


def test_context_and_authority_tokens_reject_noncanonical_base64url_mutations():
    from aquasignal.domain.context import AquaContext, AquaContextSource
    from aquasignal.integrity.authority import (
        AuthorityBinding,
        AquaAuthorityTokenError,
        AquaContextTokenError,
        issue_aqua_authority_token,
        issue_context_token,
        verify_aqua_authority_token,
        verify_context_token,
    )
    from aquasignal.domain.freshwater import FreshwaterExtractor

    secret = b"s" * 32
    context = AquaContext(source=AquaContextSource.SYNTHETIC, dataset_sha256="a" * 64, site="Stream A")
    context_token = issue_context_token(secret, context=context)
    with pytest.raises(AquaContextTokenError):
        verify_context_token(secret, context_token + "!!", context=context)
    raw, sig = context_token.split(".", 1)
    with pytest.raises(AquaContextTokenError):
        verify_context_token(secret, raw + "!!." + sig, context=context)

    source = "Visitors must avoid contact with Stream A until 18:00."
    contract = FreshwaterExtractor().extract(source)
    binding = AuthorityBinding("adv", 1, FreshwaterExtractor.profile.profile_id)
    authority_token = issue_aqua_authority_token(
        secret,
        source_text=source,
        contract=contract,
        context=context,
        binding=binding,
    )
    with pytest.raises(AquaAuthorityTokenError):
        verify_aqua_authority_token(
            secret,
            authority_token + "!!",
            source_text=source,
            contract=contract,
            context=context,
            binding=binding,
        )


def test_csv_date_range_is_not_truncated_after_500_distinct_dates():
    rows = ["site,date,indicator"]
    # Put the lexically/latest date after more than 500 distinct values so a capped
    # collector would silently publish the wrong provenance range.
    for i in range(1, 502):
        rows.append(f"Stream A,2025-01-01T{i // 60:02d}:{i % 60:02d}:00Z,x")
    rows.append("Stream A,2026-12-31T23:59:59Z,x")
    context = parse_resilience_csv(("\n".join(rows) + "\n").encode())
    assert context.date_range is not None
    assert context.date_range.endswith("2026-12-31T23:59:59Z")
    assert context.raw_summary["date_values_seen"] >= 502


def test_csv_site_dedupe_normalizes_unicode_composition():
    data = "site,date,indicator\nRiver São Pedro,2026-10-01,x\nRiver Sa\u0303o Pedro,2026-10-02,y\n".encode("utf-8")
    context = parse_resilience_csv(data)
    assert context.site == "River São Pedro"
    assert len(context.raw_summary["sites"]) == 1


def test_health_discloses_ephemeral_vs_persistent_authority_mode():
    body = client.get("/api/aqua/health").json()
    assert body["authority_secret_mode"] in {"configured-persistent", "ephemeral-development-only"}
    assert body["authority_tokens_survive_restart"] is body["authority_secret_configured"]


def test_optional_rewrite_rejects_weak_deployment_token(monkeypatch):
    monkeypatch.setenv("AQUASIGNAL_REWRITE_ENABLED", "true")
    monkeypatch.setenv("AQUASIGNAL_REWRITE_TOKEN", "short")
    response = client.post(
        "/api/aqua/rewrite",
        headers={"x-aquasignal-rewrite-token": "short"},
        json={"source_text": "Avoid direct contact with Stream A until 18:00.", "mode": "simplify", "max_chars": 360},
    )
    assert response.status_code == 503
    assert "at least 32" in response.json()["detail"]


def test_receipt_binds_exact_source_and_candidate_contracts():
    demo = client.get("/api/aqua/demo-context").json()
    source = "Visitors must avoid contact with Stream A until 18:00."
    authority = client.post(
        "/api/aqua/authority",
        json={
            "source_text": source,
            "context": demo["context"],
            "context_token": demo["context_token"],
            "advisory_id": "contract-receipt",
            "revision": 1,
        },
    ).json()
    response = client.post(
        "/api/aqua/verify",
        json={
            "source_text": source,
            "source_contract": authority["source_contract"],
            "authority_token": authority["authority_token"],
            "context": demo["context"],
            "advisory_id": "contract-receipt",
            "revision": 1,
            "candidate_text": "Visitors must avoid contact with Stream A until 18:00.",
        },
    ).json()
    receipt = response["integrity_receipt"]
    assert len(receipt["source_contract_sha256"]) == 64
    assert len(receipt["candidate_contract_sha256"]) == 64
    assert len(receipt["verification_id"].removeprefix("AQ-")) == 32

    tampered = deepcopy(receipt)
    tampered["candidate_contract_sha256"] = "0" * 64
    checked = client.post("/api/aqua/receipt/verify", json=tampered)
    assert checked.status_code == 200
    assert checked.json()["valid"] is False


def _alternate_noncanonical_b64url_tail(value: str) -> str:
    """Return a different valid-base64url spelling that decodes to the same bytes.

    Unpadded base64url strings whose length mod 4 is 2 or 3 contain unused low bits
    in the final symbol. Flipping only those unused bits creates a distinct but
    semantically identical decoding, which canonical token parsers must reject.
    """
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    idx = alphabet.index(value[-1])
    if len(value) % 4 == 3:
        # Final character carries four meaningful bits + two unused bits.
        base = idx & ~0b11
        alt = base | ((idx + 1) & 0b11)
    elif len(value) % 4 == 2:
        # Final character carries two meaningful bits + four unused bits.
        base = idx & ~0b1111
        alt = base | ((idx + 1) & 0b1111)
    else:
        raise AssertionError("test token part does not expose unused base64 pad bits")
    if alt == idx:
        alt = base | ((idx + 2) & (0b11 if len(value) % 4 == 3 else 0b1111))
    return value[:-1] + alphabet[alt]


def test_context_token_rejects_valid_alphabet_noncanonical_pad_bits():
    from aquasignal.domain.context import AquaContext, AquaContextSource
    from aquasignal.integrity.authority import AquaContextTokenError, issue_context_token, verify_context_token

    secret = b"s" * 32
    context = AquaContext(source=AquaContextSource.SYNTHETIC, dataset_sha256="a" * 64, site="Stream A")
    token = issue_context_token(secret, context=context)
    raw, sig = token.split(".", 1)
    mutated_sig = _alternate_noncanonical_b64url_tail(sig)
    with pytest.raises(AquaContextTokenError):
        verify_context_token(secret, raw + "." + mutated_sig, context=context)


def test_production_mode_refuses_ephemeral_authority_secret(tmp_path):
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    env.pop("AQUASIGNAL_AUTHORITY_SECRET", None)
    env["AQUASIGNAL_ENV"] = "production"
    proc = subprocess.run(
        [sys.executable, "-c", "import apps.aqua_api.main"],
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "AQUASIGNAL_AUTHORITY_SECRET is required" in (proc.stderr + proc.stdout)


def test_oversize_request_early_rejection_still_has_security_headers():
    response = client.post(
        "/api/aqua/context/resilience-csv",
        content=b"{}",
        headers={"content-type": "application/json", "content-length": "999999999"},
    )
    assert response.status_code == 413
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "geolocation=()" in response.headers["permissions-policy"]


def test_public_ui_does_not_expose_authenticated_optional_ai_button():
    html = (Path(__file__).resolve().parents[2] / "web_aqua" / "index.html").read_text(encoding="utf-8")
    js = (Path(__file__).resolve().parents[2] / "web_aqua" / "app.js").read_text(encoding="utf-8")
    assert "aiRewriteBtn" not in html
    assert "aiRewriteBtn" not in js


def test_csv_oversized_single_field_is_controlled_validation_error():
    from apps.aqua_api.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/aqua/context/resilience-csv",
        json={"csv_text": "x" * 300_000, "synthetic_demo": True},
    )
    assert response.status_code == 422
    assert "CSV parsing failed" in response.text


def test_resilience_csv_rejects_invalid_declared_date_value():
    from aquasignal.domain.context import parse_resilience_csv
    import pytest
    with pytest.raises(ValueError, match="ISO-8601"):
        parse_resilience_csv(b"site,date,indicator\nStream A,not-a-date,x\n")


def test_resilience_csv_accepts_iso_date_and_offset_datetime_values():
    from aquasignal.domain.context import parse_resilience_csv
    data = (
        b"site,date,indicator\n"
        b"Stream A,2026-09-15,x\n"
        b"Stream A,2026-09-16T05:30:00+05:30,y\n"
    )
    context = parse_resilience_csv(data)
    assert context.site == "Stream A"
    assert context.date_range == "2026-09-15 \u2026 2026-09-16T05:30:00+05:30"
