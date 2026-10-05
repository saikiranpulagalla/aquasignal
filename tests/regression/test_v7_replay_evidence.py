import json
from pathlib import Path

import pytest

from signallock.contracts.extractor import HeuristicExtractor
from signallock.evaluation import v7
from signallock.evaluation.holdout import HoldoutError, seal_holdout
from signallock.evaluation.v7_evidence import verify_v7_evidence
from signallock.providers.openai_http import contract_from_provider_output
import hashlib

SOURCE = "Residents must shelter indoors."
SOURCE_CONTRACT = HeuristicExtractor().extract(SOURCE, source_id="authority").model_dump(mode="json")


class EvidenceService:
    def __init__(self, provider):
        self.provider = provider

    async def extract_with_evidence(self, text, *, language="en", source_id=None, audit_metadata=None, store=False):
        base = HeuristicExtractor().extract(SOURCE, source_id=source_id).model_dump(mode="json")
        raw_output = json.dumps(base, ensure_ascii=False)
        contract = contract_from_provider_output(
            raw_output, text, language=language, source_id=source_id
        )
        return contract, {
            "response_id": f"resp-{source_id}",
            "response_model": "test-model",
            "response_created_at": 1,
            "response_completed_at": 2,
            "response_status": "completed",
            "stored": bool(store),
            "response_metadata": dict(audit_metadata or {}),
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "raw_output_text": raw_output,
            "output_text_sha256": hashlib.sha256(raw_output.encode("utf-8")).hexdigest(),
        }


def _files(tmp_path: Path):
    row = {
        "case_id": "c1",
        "source_text": SOURCE,
        "source_language": "en",
        "source_contract": SOURCE_CONTRACT,
        "candidate_text": SOURCE,
        "candidate_language": "hi",
        "expected_decision": "PASS",
        "human_reviewed": True,
        "fault_class": "clean",
    }
    src, sealed, manifest, result = (
        tmp_path / "in.jsonl",
        tmp_path / "sealed.jsonl",
        tmp_path / "manifest.json",
        tmp_path / "result.json",
    )
    src.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    seal_holdout(src, sealed, manifest, schema_version="1", verifier_version="v", extractor_version="e", prompt_version="p")
    return sealed, manifest, result


@pytest.mark.asyncio
async def test_v7_result_contains_replayable_contract_and_receipt(tmp_path, monkeypatch):
    sealed, manifest, result_path = _files(tmp_path)
    monkeypatch.setattr(v7, "ExtractionService", EvidenceService)
    report = await v7.evaluate_sealed_holdout(sealed, manifest, provider="openai", execution_binding={"provider":"openai","model":"test-model"})
    result_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    case = report["cases"][0]
    assert case["candidate_contract"]
    assert len(case["candidate_contract_sha256"]) == 64
    assert case["provider_receipt"]["response_id"].startswith("resp-")
    receipt = verify_v7_evidence(
        result_path, sealed, manifest, require_trusted_runtime=False
    )
    assert receipt["verified"] is True
    assert receipt["replayed_successful_cases"] == 1
    assert receipt["provider_receipt_cases"] == 1


@pytest.mark.asyncio
async def test_replay_verifier_rejects_decision_metric_and_contract_tampering(tmp_path, monkeypatch):
    sealed, manifest, result_path = _files(tmp_path)
    monkeypatch.setattr(v7, "ExtractionService", EvidenceService)
    report = await v7.evaluate_sealed_holdout(sealed, manifest, provider="openai", execution_binding={"provider":"openai","model":"test-model"})

    tampered = json.loads(json.dumps(report))
    tampered["cases"][0]["actual_decision"] = "BLOCK"
    result_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(HoldoutError, match="saved decision does not replay"):
        verify_v7_evidence(result_path, sealed, manifest, require_trusted_runtime=False)

    tampered = json.loads(json.dumps(report))
    tampered["metrics"]["exact_decision_accuracy"] = 0.123456
    result_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(HoldoutError, match="saved V7 metrics"):
        verify_v7_evidence(result_path, sealed, manifest, require_trusted_runtime=False)

    tampered = json.loads(json.dumps(report))
    tampered["cases"][0]["candidate_contract"]["source_id"] = "forged"
    result_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(HoldoutError, match="candidate-contract hash mismatch"):
        verify_v7_evidence(result_path, sealed, manifest, require_trusted_runtime=False)


def test_gate_rejects_old_evidence_without_provider_receipt_metric():
    metrics = {
        "total": 24,
        "dangerous_pass_rate": 0.0,
        "clean_pass_rate": 1.0,
        "clean_block_rate": 0.0,
        "exact_decision_accuracy": 1.0,
        "unsafe_block_recall": 1.0,
        "provider_error_cases": 0,
        "checkpoint_recovered_cases": 0,
        "quality": {
            "unique_sources": 8,
            "unique_source_families": 8,
            "unique_candidates": 24,
            "reviewer_count": 2,
            "fault_class_counts": {name: 2 for name in v7.V7_REQUIRED_FAULT_CLASSES},
        },
        "dangerous_pass_by_fault_class": {
            name: {"total": 2, "passes": 0, "pass_rate": 0.0}
            for name in v7.V7_REQUIRED_FAULT_CLASSES if name != "clean"
        },
        "by_language": {
            "hi": {"total": 12, "expected_pass_total": 4, "expected_block_total": 8, "dangerous_pass_rate": 0.0, "unsafe_block_recall": 1.0, "clean_pass_rate": 1.0},
            "te": {"total": 12, "expected_pass_total": 4, "expected_block_total": 8, "dangerous_pass_rate": 0.0, "unsafe_block_recall": 1.0, "clean_pass_rate": 1.0},
        },
    }
    gate = v7.evaluate_v7_gate(metrics)
    assert gate["passed"] is False
    assert any("provider response receipt" in reason for reason in gate["reasons"])


@pytest.mark.asyncio
async def test_replay_rejects_provider_model_mismatch_and_reused_response_id(tmp_path, monkeypatch):
    rows = [
        {
            "case_id": "c1", "source_text": SOURCE, "source_language": "en",
            "source_contract": SOURCE_CONTRACT, "candidate_text": SOURCE,
            "candidate_language": "hi", "expected_decision": "PASS",
            "human_reviewed": True, "fault_class": "clean",
        },
        {
            "case_id": "c2", "source_text": SOURCE, "source_language": "en",
            "source_contract": SOURCE_CONTRACT, "candidate_text": SOURCE + " ",
            "candidate_language": "te", "expected_decision": "PASS",
            "human_reviewed": True, "fault_class": "clean",
        },
    ]
    src, sealed, manifest, result_path = (
        tmp_path / "in2.jsonl", tmp_path / "sealed2.jsonl", tmp_path / "manifest2.json", tmp_path / "result2.json"
    )
    src.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    seal_holdout(src, sealed, manifest, schema_version="1", verifier_version="v", extractor_version="e", prompt_version="p")
    monkeypatch.setattr(v7, "ExtractionService", EvidenceService)
    report = await v7.evaluate_sealed_holdout(
        sealed, manifest, provider="openai", execution_binding={"provider":"openai","model":"test-model"}
    )

    tampered = json.loads(json.dumps(report))
    tampered["cases"][0]["provider_receipt"]["response_model"] = "fallback-model"
    result_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(HoldoutError, match="differs from frozen model"):
        verify_v7_evidence(result_path, sealed, manifest, require_trusted_runtime=False)

    tampered = json.loads(json.dumps(report))
    tampered["cases"][1]["provider_receipt"]["response_id"] = tampered["cases"][0]["provider_receipt"]["response_id"]
    result_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(HoldoutError, match="response_id is reused"):
        verify_v7_evidence(result_path, sealed, manifest, require_trusted_runtime=False)


@pytest.mark.asyncio
async def test_production_replay_recomputes_manifest_quality_instead_of_trusting_it(tmp_path, monkeypatch):
    from signallock.evaluation.holdout import _runtime_binding
    import signallock.evaluation.v7_evidence as evidence

    sealed, manifest_path, result_path = _files(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["strict_v7"] = True
    manifest["quality"] = {"forged": 1}
    manifest["runtime_binding"] = _runtime_binding(provider="openai", model="test-model", provider_config={"store": False})
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr(v7, "ExtractionService", EvidenceService)
    report = await v7.evaluate_sealed_holdout(
        sealed, manifest_path, provider="openai", execution_binding={"provider":"openai","model":"test-model"}
    )
    result_path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(evidence, "validate_v7_quality", lambda rows: {"real": 1})
    with pytest.raises(HoldoutError, match="quality block does not match"):
        verify_v7_evidence(result_path, sealed, manifest_path, require_trusted_runtime=True)
