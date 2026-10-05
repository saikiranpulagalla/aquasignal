import json
from pathlib import Path

import pytest

from signallock.contracts.extractor import HeuristicExtractor
from signallock.evaluation import v7
from signallock.evaluation.holdout import seal_holdout

SOURCE = "Residents must shelter indoors."
SOURCE_CONTRACT = HeuristicExtractor().extract(SOURCE, source_id="authority").model_dump(mode="json")


def _write_rows(path: Path):
    rows = [
        {"case_id":"p1","source_text":SOURCE,"source_language":"en","source_contract":SOURCE_CONTRACT,"candidate_text":"SAFE","candidate_language":"hi","expected_decision":"PASS","human_reviewed":True,"fault_class":"clean"},
        {"case_id":"b1","source_text":SOURCE,"source_language":"en","source_contract":SOURCE_CONTRACT,"candidate_text":"UNSAFE","candidate_language":"te","expected_decision":"BLOCK","human_reviewed":True,"fault_class":"modality"},
    ]
    path.write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in rows), encoding="utf-8")
    return rows


class FakeService:
    def __init__(self, provider): self.provider = provider
    async def extract(self, text, *, language="en", source_id=None):
        if text == "UNSAFE":
            return HeuristicExtractor().extract("Residents must evacuate immediately.", source_id=source_id)
        return HeuristicExtractor().extract(SOURCE, source_id=source_id)


class FailingService:
    def __init__(self, provider): self.provider = provider
    async def extract(self, *a, **kw):
        raise RuntimeError("provider unavailable")


def _seal(tmp_path: Path):
    src, sealed, manifest = tmp_path/"in.jsonl", tmp_path/"sealed.jsonl", tmp_path/"manifest.json"
    _write_rows(src)
    seal_holdout(src, sealed, manifest, schema_version="1", verifier_version="v", extractor_version="e", prompt_version="p")
    return sealed, manifest


@pytest.mark.asyncio
async def test_preexisting_checkpoint_is_refused_for_fresh_certification(tmp_path, monkeypatch):
    sealed, manifest = _seal(tmp_path)
    checkpoint = tmp_path/"checkpoint.json"
    checkpoint.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(v7, "ExtractionService", FakeService)
    with pytest.raises(ValueError, match="certification runs must start fresh"):
        await v7.evaluate_sealed_holdout(
            sealed, manifest, provider="openai", checkpoint_path=checkpoint,
            execution_binding={"model":"m"}, allow_checkpoint_recovery=False,
        )


@pytest.mark.asyncio
async def test_resume_is_bound_to_exact_case_inputs_and_never_qualifies(tmp_path, monkeypatch):
    sealed, manifest = _seal(tmp_path)
    checkpoint = tmp_path/"checkpoint.json"
    monkeypatch.setattr(v7, "ExtractionService", FakeService)
    first = await v7.evaluate_sealed_holdout(
        sealed, manifest, provider="openai", checkpoint_path=checkpoint,
        execution_binding={"model":"m"}, allow_checkpoint_recovery=False,
    )
    assert checkpoint.exists()
    resumed = await v7.evaluate_sealed_holdout(
        sealed, manifest, provider="openai", checkpoint_path=checkpoint,
        execution_binding={"model":"m"}, allow_checkpoint_recovery=True,
    )
    assert resumed["metrics"]["checkpoint_recovered_cases"] == 2
    assert resumed["metrics"]["live_executed_cases"] == 0
    assert any("checkpoint-recovered" in r for r in resumed["gate"]["reasons"])

    payload=json.loads(checkpoint.read_text(encoding="utf-8"))
    payload["cases"][0]["case_input_sha256"]="0"*64
    checkpoint.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="case input hash mismatch"):
        await v7.evaluate_sealed_holdout(
            sealed, manifest, provider="openai", checkpoint_path=checkpoint,
            execution_binding={"model":"m"}, allow_checkpoint_recovery=True,
        )


@pytest.mark.asyncio
async def test_provider_errors_are_reported_and_disqualify_gate(tmp_path, monkeypatch):
    sealed, manifest = _seal(tmp_path)
    monkeypatch.setattr(v7, "ExtractionService", FailingService)
    report = await v7.evaluate_sealed_holdout(
        sealed, manifest, provider="openai", checkpoint_path=None,
        max_attempts=1, execution_binding={"model":"m"},
    )
    assert report["metrics"]["provider_error_cases"] == 2
    assert report["gate"]["passed"] is False
    assert any("provider error cases" in r for r in report["gate"]["reasons"])


def test_gate_rejects_checkpoint_recovery_and_provider_error_even_if_other_metrics_are_green():
    metrics = {
        "total": 24, "dangerous_pass_rate": 0.0, "clean_pass_rate": 1.0,
        "clean_block_rate": 0.0, "exact_decision_accuracy": 1.0, "unsafe_block_recall": 1.0,
        "provider_error_cases": 1, "missing_provider_receipt_cases": 0, "checkpoint_recovered_cases": 1,
        "quality": {"unique_sources": 8, "unique_source_families": 8, "unique_candidates": 24, "reviewer_count": 2,
                    "fault_class_counts": {name: 2 for name in v7.V7_REQUIRED_FAULT_CLASSES}},
        "dangerous_pass_by_fault_class": {name:{"total":2,"passes":0,"pass_rate":0.0} for name in v7.V7_REQUIRED_FAULT_CLASSES if name!="clean"},
        "by_language": {
            "hi":{"total":12,"expected_pass_total":6,"expected_block_total":6,"dangerous_pass_rate":0.0,"unsafe_block_recall":1.0,"clean_pass_rate":1.0},
            "te":{"total":12,"expected_pass_total":6,"expected_block_total":6,"dangerous_pass_rate":0.0,"unsafe_block_recall":1.0,"clean_pass_rate":1.0},
        },
    }
    gate=v7.evaluate_v7_gate(metrics)
    assert gate["passed"] is False
    assert any("provider error" in r for r in gate["reasons"])
    assert any("checkpoint-recovered" in r for r in gate["reasons"])
