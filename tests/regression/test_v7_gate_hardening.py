import json
from pathlib import Path

import pytest

from signallock.contracts.extractor import HeuristicExtractor
from signallock.evaluation.holdout import (
    HoldoutError,
    _runtime_binding,
    seal_v7_holdout_strict,
    verify_v7_runtime_binding,
)


def _write(path: Path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def test_strict_v7_sealer_rejects_english_text_mislabeled_hi_te(tmp_path):
    source = "Residents must shelter indoors."
    contract = HeuristicExtractor().extract(source, source_id="authority").model_dump(mode="json")
    rows = []
    for lang in ("hi", "te"):
        for i in range(12):
            rows.append({
                "case_id": f"{lang}-{i}", "source_text": source, "source_language": "en",
                "source_contract": contract, "candidate_text": "Residents must shelter indoors.",
                "candidate_language": lang, "expected_decision": "PASS" if i < 4 else "BLOCK",
                "human_reviewed": True, "reviewer_id": "r1", "reviewed_at": "2026-09-12T10:00:00+05:30",
                "source_reference": "fixture", "fault_class": "clean" if i < 4 else "modality",
                "second_reviewer_id": "r2",
            })
    inp = tmp_path / "in.jsonl"; _write(inp, rows)
    with pytest.raises(HoldoutError, match="independently validate"):
        seal_v7_holdout_strict(
            inp, tmp_path / "out.jsonl", tmp_path / "manifest.json",
            schema_version="1.0", verifier_version="v", extractor_version="e", prompt_version="p",
            code_commit="abc", provider="openai", model="gpt-test",
        )


def test_v7_runtime_binding_detects_model_change():
    manifest = {"strict_v7": True, "runtime_binding": _runtime_binding(provider="openai", model="model-a")}
    verify_v7_runtime_binding(manifest, provider="openai", model="model-a")
    with pytest.raises(HoldoutError, match="provider/model mismatch"):
        verify_v7_runtime_binding(manifest, provider="openai", model="model-b")
