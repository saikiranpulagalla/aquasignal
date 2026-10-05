import json
from pathlib import Path

import pytest

from signallock.contracts.extractor import HeuristicExtractor
from signallock.evaluation.holdout import HoldoutError, seal_holdout, verify_seal


SOURCE = "Residents must shelter indoors."


def _row(case_id="h1", reviewed=True):
    contract = HeuristicExtractor().extract(SOURCE, source_id="authority").model_dump(mode="json")
    return {
        "case_id": case_id,
        "source_text": SOURCE,
        "source_language": "en",
        "source_contract": contract,
        "candidate_text": "घर के अंदर रहें।",
        "candidate_language": "hi",
        "expected_decision": "PASS",
        "human_reviewed": reviewed,
    }


def _write(path: Path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def test_seal_and_verify_round_trip(tmp_path):
    src, out, man = tmp_path/"in.jsonl", tmp_path/"sealed.jsonl", tmp_path/"manifest.json"
    _write(src, [_row()])
    manifest = seal_holdout(src, out, man, schema_version="1.0", verifier_version="v", extractor_version="e", prompt_version="p")
    assert manifest["sealed"] is True
    assert manifest["language_pairs"] == ["en->hi"]
    assert verify_seal(out, man)["sha256"] == manifest["sha256"]


def test_refuses_unreviewed_holdout(tmp_path):
    src = tmp_path/"in.jsonl"; _write(src, [_row(reviewed=False)])
    with pytest.raises(HoldoutError, match="human reviewed"):
        seal_holdout(src, tmp_path/"o", tmp_path/"m", schema_version="1", verifier_version="v", extractor_version="e", prompt_version="p")


def test_refuses_duplicate_case_ids(tmp_path):
    src = tmp_path/"in.jsonl"; _write(src, [_row(), _row()])
    with pytest.raises(HoldoutError, match="unique"):
        seal_holdout(src, tmp_path/"o", tmp_path/"m", schema_version="1", verifier_version="v", extractor_version="e", prompt_version="p")


def test_tamper_is_detected(tmp_path):
    src, out, man = tmp_path/"in.jsonl", tmp_path/"sealed.jsonl", tmp_path/"manifest.json"
    _write(src, [_row()])
    seal_holdout(src, out, man, schema_version="1", verifier_version="v", extractor_version="e", prompt_version="p")
    out.write_text(out.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(HoldoutError, match="hash mismatch"):
        verify_seal(out, man)


def test_refuses_tampered_source_contract_provenance(tmp_path):
    row = _row()
    row["source_contract"]["required_actions"][0]["evidence"]["quote"] = "fabricated"
    src = tmp_path/"in.jsonl"; _write(src, [row])
    with pytest.raises(HoldoutError, match="provenance"):
        seal_holdout(src, tmp_path/"o", tmp_path/"m", schema_version="1", verifier_version="v", extractor_version="e", prompt_version="p")


def test_refuses_inconsistent_oracle_for_same_source(tmp_path):
    row1 = _row(case_id="a")
    row2 = _row(case_id="b")
    row2["source_contract"]["audience"] = ["visitors"]
    src = tmp_path/"in.jsonl"; _write(src, [row1, row2])
    with pytest.raises(HoldoutError, match="inconsistent frozen"):
        seal_holdout(src, tmp_path/"o", tmp_path/"m", schema_version="1", verifier_version="v", extractor_version="e", prompt_version="p")


def test_code_binding_rejects_mismatched_runtime_commit(tmp_path):
    from signallock.evaluation.holdout import verify_code_binding
    row = _row()
    src, out, man = tmp_path/"in.jsonl", tmp_path/"sealed.jsonl", tmp_path/"manifest.json"
    _write(src, [row])
    manifest = seal_holdout(src, out, man, schema_version="1", verifier_version="v", extractor_version="e", prompt_version="p", code_commit="abc123")
    verify_code_binding(manifest, "abc123")
    with pytest.raises(HoldoutError, match="code commit mismatch"):
        verify_code_binding(manifest, "different")
