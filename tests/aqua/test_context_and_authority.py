import json

import pytest

from aquasignal.domain.context import AquaContext, AquaContextSource, parse_oah_fhir_json, parse_resilience_csv
from aquasignal.domain.freshwater import FreshwaterExtractor, FreshwaterProfile
from aquasignal.integrity.authority import (
    AquaAuthorityTokenError,
    AuthorityBinding,
    issue_aqua_authority_token,
    verify_aqua_authority_token,
)


def test_parse_resilience_csv_is_provenance_not_risk_inference():
    data = b"site,date,pathogen_indicator,precipitation\nStream A,2026-09-15,example,12\n"
    context = parse_resilience_csv(data, synthetic_demo=True)
    assert context.source == AquaContextSource.RESILIENCE_COMPATIBLE_CSV
    assert context.site == "Stream A"
    assert context.synthetic_demo is True
    assert "pathogen_indicator" in context.indicators


def test_fhir_import_rejects_patient_data():
    with pytest.raises(ValueError):
        parse_oah_fhir_json(json.dumps({"resourceType": "Patient", "id": "x"}).encode())


def test_fhir_observation_context_is_accepted_without_certification_claim():
    payload = {
        "resourceType": "Observation",
        "id": "obs-1",
        "meta": {"profile": ["https://example.test/oah/StructureDefinition/observation-indicators-oah"]},
        "status": "final",
        "code": {"text": "Demo environmental indicator"},
        "subject": {"reference": "Location/stream-a", "display": "Stream A"},
    }
    context = parse_oah_fhir_json(json.dumps(payload).encode(), synthetic_demo=True)
    assert context.resource_type == "Observation"
    assert context.site == "Stream A"


def test_authority_token_binds_context_revision_profile_and_source():
    ext = FreshwaterExtractor()
    text = "Visitors must avoid contact with Stream A until 18:00."
    contract = ext.extract(text, source_id="authority")
    context = AquaContext(
        source=AquaContextSource.SYNTHETIC,
        dataset_sha256="a" * 64,
        site="Stream A",
        synthetic_demo=True,
    )
    binding = AuthorityBinding("adv-1", 1, FreshwaterProfile().profile_id)
    token = issue_aqua_authority_token(b"secret", source_text=text, contract=contract, context=context, binding=binding)
    verify_aqua_authority_token(b"secret", token, source_text=text, contract=contract, context=context, binding=binding)

    changed = context.model_copy(update={"site": "Stream B"})
    with pytest.raises(AquaAuthorityTokenError):
        verify_aqua_authority_token(b"secret", token, source_text=text, contract=contract, context=changed, binding=binding)


def test_context_alignment_detects_named_site_mismatch():
    from aquasignal.domain.context import assess_context_alignment
    ext = FreshwaterExtractor()
    contract = ext.extract("Visitors must avoid contact with Stream B until 18:00.")
    context = AquaContext(source=AquaContextSource.SYNTHETIC, dataset_sha256="b" * 64, site="Stream A", synthetic_demo=True)
    status, _ = assess_context_alignment(context, contract)
    assert status == "MISMATCH"


def test_context_alignment_preserves_single_letter_site_identifier():
    from aquasignal.domain.context import assess_context_alignment
    ext = FreshwaterExtractor()
    a = AquaContext(source=AquaContextSource.SYNTHETIC, dataset_sha256="c" * 64, site="Stream A", synthetic_demo=True)
    contract_a = ext.extract("Avoid direct contact with Stream A until 18:00.")
    contract_b = ext.extract("Avoid direct contact with Stream B until 18:00.")
    assert assess_context_alignment(a, contract_a)[0] == "MATCH"
    assert assess_context_alignment(a, contract_b)[0] == "MISMATCH"


def test_resilience_csv_multi_site_context_does_not_pretend_to_be_single_site():
    data = b"site,date,indicator\nStream A,2026-09-15,x\nStream B,2026-09-16,y\n"
    context = parse_resilience_csv(data)
    assert context.site is None
    assert context.date_range == "2026-09-15 \u2026 2026-09-16"
    assert context.raw_summary["sites"] == ["Stream A", "Stream B"]


def test_resilience_csv_rejects_header_only_context():
    with pytest.raises(ValueError):
        parse_resilience_csv(b"site,date,indicator\n")


def test_fhir_reference_only_site_is_provenance_not_false_mismatch():
    from aquasignal.domain.context import assess_context_alignment
    payload = {
        "resourceType": "Observation",
        "id": "obs-ref-only",
        "status": "final",
        "code": {"text": "Environmental indicator"},
        "subject": {"reference": "Location/123"},
    }
    context = parse_oah_fhir_json(json.dumps(payload).encode(), synthetic_demo=True)
    contract = FreshwaterExtractor().extract("Avoid direct contact with Stream A until 18:00.")
    status, _ = assess_context_alignment(context, contract)
    assert status == "UNKNOWN"


def test_context_alignment_accepts_supported_relational_scope_on_same_waterbody():
    from aquasignal.domain.context import assess_context_alignment
    ext = FreshwaterExtractor()
    context = AquaContext(
        source=AquaContextSource.SYNTHETIC,
        dataset_sha256="d" * 64,
        site="Stream A",
        synthetic_demo=True,
    )
    downstream = ext.extract("Visitors must avoid contact with Stream A downstream of Bridge A after 18:00.")
    upstream = ext.extract("Visitors must avoid contact with Stream A upstream of Bridge A until 18:00.")
    assert assess_context_alignment(context, downstream)[0] == "MATCH"
    assert assess_context_alignment(context, upstream)[0] == "MATCH"


def test_context_alignment_relational_scope_does_not_loosen_named_site_identity():
    from aquasignal.domain.context import assess_context_alignment
    ext = FreshwaterExtractor()
    context = AquaContext(
        source=AquaContextSource.SYNTHETIC,
        dataset_sha256="e" * 64,
        site="Stream A",
        synthetic_demo=True,
    )
    wrong_site = ext.extract("Visitors must avoid contact with Stream B downstream of Bridge A after 18:00.")
    similar_name = ext.extract("Visitors must avoid contact with Stream AB downstream of Bridge A after 18:00.")
    assert assess_context_alignment(context, wrong_site)[0] == "MISMATCH"
    assert assess_context_alignment(context, similar_name)[0] == "MISMATCH"
