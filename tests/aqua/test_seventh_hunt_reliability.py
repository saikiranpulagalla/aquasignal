from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.aqua_api.main import app
from aquasignal.domain.context import parse_resilience_csv


client = TestClient(app)


def test_csv_rejects_conflicting_date_and_timestamp_aliases():
    data = (
        "site,date,timestamp,temp\n"
        "Stream A,2026-10-01,2026-10-02T12:00:00Z,20\n"
    ).encode()
    with pytest.raises(ValueError, match="conflicting date/time metadata"):
        parse_resilience_csv(data)


def test_csv_rejects_conflicting_full_datetime_aliases():
    data = (
        "site,datetime,timestamp,temp\n"
        "Stream A,2026-10-01T12:00:00Z,2026-10-01T13:00:00Z,20\n"
    ).encode()
    with pytest.raises(ValueError, match="conflicting date/time metadata"):
        parse_resilience_csv(data)


def test_csv_accepts_date_and_timestamp_on_same_calendar_date():
    data = (
        "site,date,timestamp,temp\n"
        "Stream A,2026-10-01,2026-10-01T12:00:00Z,20\n"
    ).encode()
    context = parse_resilience_csv(data)
    assert context.date_range == "2026-10-01T12:00:00Z"


def test_csv_accepts_equivalent_full_timestamps_with_different_offsets():
    data = (
        "site,datetime,timestamp,temp\n"
        "Stream A,2026-10-01T12:00:00Z,2026-10-01T13:00:00+01:00,20\n"
    ).encode()
    context = parse_resilience_csv(data)
    assert context.date_range == "2026-10-01T12:00:00Z"


def test_csv_accepts_separate_date_and_time_columns():
    data = (
        "site,date,time,temp\n"
        "Stream A,2026-10-01,18:00,20\n"
    ).encode()
    context = parse_resilience_csv(data)
    assert context.date_range == "2026-10-01"


def test_csv_rejects_invalid_secondary_datetime_alias_even_if_not_selected():
    data = (
        "site,datetime,timestamp,temp\n"
        "Stream A,2026-10-01T12:00:00Z,not-a-date,20\n"
    ).encode()
    with pytest.raises(ValueError, match="ISO-8601"):
        parse_resilience_csv(data)


def test_read_only_runtime_serves_core_endpoints(tmp_path: Path):
    # This test uses a subprocess because Python import bytecode writes and cwd
    # behavior are process-level properties. The app itself must not require a
    # writable source tree at runtime.
    root = Path(__file__).resolve().parents[2]
    script = """
from fastapi.testclient import TestClient
from apps.aqua_api.main import app
c=TestClient(app)
assert c.get('/api/aqua/health').status_code == 200
assert c.get('/api/aqua/ready').status_code == 200
assert c.get('/').status_code == 200
"""
    env = dict(os.environ)
    env.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "AQUASIGNAL_ENV": "production",
        "AQUASIGNAL_AUTHORITY_SECRET": "0123456789abcdef0123456789abcdef",
    })
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_api_unknown_fields_are_rejected_not_ignored():
    demo = client.get("/api/aqua/demo-context").json()
    response = client.post(
        "/api/aqua/authority",
        json={
            "source_text": "Do not swim in Stream A until 18:00.",
            "context": demo["context"],
            "context_token": demo["context_token"],
            "advisory_id": "strict-contract",
            "revision": 1,
            "revission": 2,
        },
    )
    assert response.status_code == 422
    assert "extra_forbidden" in response.text


def test_api_validation_does_not_echo_invalid_advisory_value():
    secret_marker = "VERY-SENSITIVE-ADVISORY-CONTENT"
    response = client.post(
        "/api/aqua/authority",
        json={
            "source_text": [secret_marker],
            "context": {},
            "context_token": "x" * 20,
            "advisory_id": "x",
            "revision": 1,
        },
    )
    assert response.status_code == 422
    assert secret_marker not in response.text


def test_csv_date_range_uses_rowwise_fallback_across_compatible_aliases():
    data = (
        "site,date,timestamp,temp\n"
        "Stream A,2026-10-01,,20\n"
        "Stream A,2026-10-02,2026-10-02T12:00:00Z,21\n"
    ).encode()
    context = parse_resilience_csv(data)
    assert context.date_range == "2026-10-01 … 2026-10-02T12:00:00Z"


def test_csv_date_range_prefers_precise_alias_per_row_without_losing_fallback_rows():
    data = (
        "site,date,datetime,temp\n"
        "Stream A,2026-10-01,2026-10-01T18:00:00Z,20\n"
        "Stream A,2026-10-02,,21\n"
    ).encode()
    context = parse_resilience_csv(data)
    assert context.date_range == "2026-10-01T18:00:00Z … 2026-10-02"


def test_authority_and_receipt_bind_exact_submitted_advisory_text():
    import hashlib

    demo = client.get('/api/aqua/demo-context').json()
    source_text = "  Do not swim in Stream A until 18:00.\n"
    authority = client.post(
        '/api/aqua/authority',
        json={
            'source_text': source_text,
            'context': demo['context'],
            'context_token': demo['context_token'],
            'advisory_id': 'exact-text-binding',
            'revision': 1,
        },
    )
    assert authority.status_code == 200, authority.text
    body = authority.json()

    verified = client.post(
        '/api/aqua/verify',
        json={
            'source_text': source_text,
            'source_contract': body['source_contract'],
            'authority_token': body['authority_token'],
            'context': demo['context'],
            'advisory_id': 'exact-text-binding',
            'revision': 1,
            'candidate_text': '  Do not swim in Stream A until 18:00.\n',
        },
    )
    assert verified.status_code == 200, verified.text
    result = verified.json()
    assert result['decision'] == 'PASS'
    assert result['integrity_receipt']['source_sha256'] == hashlib.sha256(source_text.encode('utf-8')).hexdigest()
    candidate_text = '  Do not swim in Stream A until 18:00.\n'
    assert result['integrity_receipt']['candidate_sha256'] == hashlib.sha256(candidate_text.encode('utf-8')).hexdigest()

    # Semantically harmless whitespace must not mutate the provenance identity of an
    # already signed source.  A trimmed source needs a fresh authority token.
    rebound = client.post(
        '/api/aqua/verify',
        json={
            'source_text': source_text.strip(),
            'source_contract': body['source_contract'],
            'authority_token': body['authority_token'],
            'context': demo['context'],
            'advisory_id': 'exact-text-binding',
            'revision': 1,
            'candidate_text': 'Do not swim in Stream A until 18:00.',
        },
    )
    assert rebound.status_code == 409
    assert 'different advisory text' in rebound.text


def test_csv_time_only_metadata_is_accepted_without_inventing_a_date_range():
    data = (
        "site,time,temp\n"
        "Stream A,18:00,20\n"
        "Stream A,19:30,21\n"
    ).encode()
    context = parse_resilience_csv(data)
    assert context.date_range is None
    assert context.indicators == ["temp"]
    assert context.raw_summary["date_field"] == "time"
    assert context.raw_summary["date_values_seen"] == 0


def test_extreme_json_integer_is_controlled_not_500_and_keeps_security_headers():
    client_no_raise = TestClient(app, raise_server_exceptions=False)
    body = (
        '{"source_text":"Do not swim in Stream A until 18:00.",'
        '"context":{},"context_token":"xxxxxxxxxxxxxxxxxxxx",'
        '"advisory_id":"x","revision":' + ('9' * 5000) + '}'
    )
    response = client_no_raise.post(
        '/api/aqua/authority',
        content=body,
        headers={'content-type': 'application/json'},
    )
    assert response.status_code == 422
    assert 'parser limit' in response.text.casefold() or 'numeric' in response.text.casefold()
    assert response.headers.get('cache-control') == 'no-store'
    assert response.headers.get('content-security-policy')
