import json
from pathlib import Path

import pytest

from signallock.evaluation import v7
from signallock.evaluation.holdout import seal_holdout
from signallock.contracts.extractor import HeuristicExtractor


SOURCE = "Residents must shelter indoors."
SOURCE_CONTRACT = HeuristicExtractor().extract(SOURCE, source_id="authority").model_dump(mode="json")


class FakeExtractor:
    async def extract(self, text, *, language="en", source_id=None):
        # Tests orchestration/metrics only. Semantic provider behavior has separate tests.
        if "UNSAFE" in text:
            return HeuristicExtractor().extract("Residents must evacuate immediately.", source_id=source_id)
        return HeuristicExtractor().extract(SOURCE, source_id=source_id)


class FakeService:
    def __init__(self, provider): self.provider = provider
    async def extract(self, *a, **kw): return await FakeExtractor().extract(*a, **kw)


def _write_rows(path: Path):
    rows = [
        {"case_id":"p1","source_text":SOURCE,"source_language":"en","source_contract":SOURCE_CONTRACT,"candidate_text":"SAFE","candidate_language":"hi","expected_decision":"PASS","human_reviewed":True},
        {"case_id":"b1","source_text":SOURCE,"source_language":"en","source_contract":SOURCE_CONTRACT,"candidate_text":"UNSAFE","candidate_language":"te","expected_decision":"BLOCK","human_reviewed":True},
    ]
    path.write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in rows), encoding="utf-8")


@pytest.mark.asyncio
async def test_v7_reports_language_and_dangerous_pass_metrics(tmp_path, monkeypatch):
    src, sealed, manifest = tmp_path/"in.jsonl", tmp_path/"sealed.jsonl", tmp_path/"manifest.json"
    _write_rows(src)
    seal_holdout(src, sealed, manifest, schema_version="1", verifier_version="v", extractor_version="e", prompt_version="p")
    monkeypatch.setattr(v7, "ExtractionService", FakeService)
    report = await v7.evaluate_sealed_holdout(sealed, manifest, provider="openai")
    assert report["metrics"]["dangerous_pass_rate"] == 0.0
    assert report["metrics"]["clean_pass_rate"] == 1.0
    assert set(report["metrics"]["by_language"]) == {"hi", "te"}


def test_v7_gate_refuses_tiny_or_undercovered_evaluation():
    metrics = {
        "total": 2,
        "dangerous_pass_rate": 0.0,
        "clean_pass_rate": 1.0,
        "exact_decision_accuracy": 1.0,
        "by_language": {
            "hi": {"total": 1, "expected_pass_total": 1, "expected_block_total": 0, "dangerous_pass_rate": None, "clean_pass_rate": 1.0},
            "te": {"total": 1, "expected_pass_total": 0, "expected_block_total": 1, "dangerous_pass_rate": 0.0, "clean_pass_rate": None},
        },
    }
    gate = v7.evaluate_v7_gate(metrics)
    assert gate["passed"] is False
    assert any("24" in reason for reason in gate["reasons"])


def test_v7_gate_rejects_old_numeric_only_metrics_without_diversity_evidence():
    metrics = {
        "total": 32,
        "dangerous_pass_rate": 0.0,
        "clean_pass_rate": 0.90,
        "clean_block_rate": 0.0,
        "exact_decision_accuracy": 0.94,
        "by_language": {
            "hi": {"total": 16, "expected_pass_total": 6, "expected_block_total": 10, "dangerous_pass_rate": 0.0, "unsafe_block_recall": 1.0, "clean_pass_rate": 0.83},
            "te": {"total": 16, "expected_pass_total": 6, "expected_block_total": 10, "dangerous_pass_rate": 0.0, "unsafe_block_recall": 1.0, "clean_pass_rate": 0.83},
        },
    }
    gate = v7.evaluate_v7_gate(metrics)
    assert gate["passed"] is False
    assert any("diversity" in reason or "fault" in reason for reason in gate["reasons"])


def test_v7_gate_accepts_sufficient_balanced_metrics_with_quality_and_zero_relational_passes():
    fault_classes = {name: 2 for name in v7.V7_REQUIRED_FAULT_CLASSES}
    metrics = {
        "total": 32,
        "dangerous_pass_rate": 0.0,
        "clean_pass_rate": 0.90,
        "clean_block_rate": 0.0,
        "exact_decision_accuracy": 0.94,
        "unsafe_block_recall": 1.0,
        "provider_error_cases": 0,
        "missing_provider_receipt_cases": 0,
        "missing_stored_provider_receipt_cases": 0,
        "checkpoint_recovered_cases": 0,
        "quality": {
            "unique_sources": 8,
            "unique_source_families": 8,
            "unique_candidates": 24,
            "reviewer_count": 2,
            "fault_class_counts": fault_classes,
        },
        "dangerous_pass_by_fault_class": {
            name: {"total": 2, "passes": 0, "pass_rate": 0.0}
            for name in v7.V7_REQUIRED_FAULT_CLASSES if name != "clean"
        },
        "by_language": {
            "hi": {"total": 16, "expected_pass_total": 6, "expected_block_total": 10, "dangerous_pass_rate": 0.0, "unsafe_block_recall": 1.0, "clean_pass_rate": 0.83},
            "te": {"total": 16, "expected_pass_total": 6, "expected_block_total": 10, "dangerous_pass_rate": 0.0, "unsafe_block_recall": 1.0, "clean_pass_rate": 0.83},
        },
    }
    assert v7.evaluate_v7_gate(metrics)["passed"] is True
