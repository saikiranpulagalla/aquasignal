import hashlib
import json
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest

from signallock.contracts.extractor import HeuristicExtractor
from signallock.evaluation import v7
from signallock.evaluation.holdout import HoldoutError, seal_holdout
from signallock.evaluation.v7_provider_evidence import verify_v7_provider_evidence
from signallock.evaluation.v7_evidence import verify_v7_evidence
from signallock.providers.openai_http import EXTRACTION_SYSTEM_PROMPT

SOURCE = "Residents must shelter indoors."
SOURCE_CONTRACT = HeuristicExtractor().extract(SOURCE, source_id="authority").model_dump(mode="json")


class StoredEvidenceService:
    responses = {}

    def __init__(self, provider):
        self.provider = provider

    async def extract_with_evidence(
        self, text, *, language="en", source_id=None, audit_metadata=None, store=False
    ):
        contract = HeuristicExtractor().extract(text, language=language, source_id=source_id)
        raw_output = json.dumps(contract.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        response_id = f"resp_{source_id.replace(':', '_')}"
        user_input = f"Language: {language}\nSource ID: {source_id or ''}\n\nALERT:\n{text}"
        raw_response = {
            "id": response_id,
            "object": "response",
            "created_at": 1000,
            "completed_at": 1001,
            "status": "completed",
            "model": "test-model",
            "store": bool(store),
            "metadata": dict(audit_metadata or {}),
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": raw_output}],
            }],
            "usage": {"input_tokens": 10, "output_tokens": 10, "total_tokens": 20},
        }
        input_items = {
            "object": "list",
            "data": [
                {"id": "sys", "type": "message", "role": "system", "content": [{"type": "input_text", "text": EXTRACTION_SYSTEM_PROMPT}]},
                {"id": "usr", "type": "message", "role": "user", "content": [{"type": "input_text", "text": user_input}]},
            ],
            "has_more": False,
        }
        self.responses[response_id] = (raw_response, input_items)
        return contract, {
            "response_id": response_id,
            "response_model": "test-model",
            "response_created_at": 1000,
            "response_completed_at": 1001,
            "response_status": "completed",
            "stored": bool(store),
            "response_metadata": dict(audit_metadata or {}),
            "usage": raw_response["usage"],
            "raw_output_text": raw_output,
            "output_text_sha256": hashlib.sha256(raw_output.encode("utf-8")).hexdigest(),
        }


def _fixture(tmp_path: Path):
    row = {
        "case_id": "c1",
        "source_text": SOURCE,
        "source_language": "en",
        "source_contract": SOURCE_CONTRACT,
        "candidate_text": SOURCE,
        "candidate_language": "en",
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


def _mock_client(*, tamper_input=False, tamper_output=False, tamper_prompt=False, tamper_metadata=False, missing=False):
    async def handler(request: httpx.Request) -> httpx.Response:
        path = unquote(request.url.path)
        if path.endswith("/input_items"):
            response_id = path.split("/")[-2]
            if missing or response_id not in StoredEvidenceService.responses:
                return httpx.Response(404, json={"error": {"message": "not found"}})
            _, items = StoredEvidenceService.responses[response_id]
            items = json.loads(json.dumps(items))
            if tamper_input:
                items["data"][-1]["content"][0]["text"] += " tampered"
            if tamper_prompt:
                items["data"][0]["content"][0]["text"] += " tampered"
            return httpx.Response(200, json=items)
        response_id = path.split("/")[-1]
        if missing or response_id not in StoredEvidenceService.responses:
            return httpx.Response(404, json={"error": {"message": "not found"}})
        raw, _ = StoredEvidenceService.responses[response_id]
        raw = json.loads(json.dumps(raw))
        if tamper_output:
            raw["output"][0]["content"][0]["text"] += " "
        if tamper_metadata:
            raw["metadata"]["signallock_case_id"] = "wrong-case"
        return httpx.Response(200, json=raw)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.openai.com")


@pytest.mark.asyncio
async def test_live_provider_retrieval_binds_response_input_output_and_metadata(tmp_path, monkeypatch):
    StoredEvidenceService.responses = {}
    sealed, manifest, result_path = _fixture(tmp_path)
    monkeypatch.setattr(v7, "ExtractionService", StoredEvidenceService)
    report = await v7.evaluate_sealed_holdout(
        sealed,
        manifest,
        provider="openai",
        execution_binding={"provider": "openai", "model": "test-model", "runtime_fingerprint_sha256": "f" * 64},
    )
    result_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    client = _mock_client()
    try:
        receipt = await verify_v7_provider_evidence(
            result_path, sealed, manifest, require_trusted_runtime=False, api_key="test", client=client
        )
    finally:
        await client.aclose()
    assert receipt["verified"] is True
    assert receipt["provider_verified_cases"] == 1
    assert receipt["cases"][0]["response_id"].startswith("resp_")


@pytest.mark.asyncio
async def test_live_provider_retrieval_rejects_locally_fabricated_response_id(tmp_path, monkeypatch):
    StoredEvidenceService.responses = {}
    sealed, manifest, result_path = _fixture(tmp_path)
    monkeypatch.setattr(v7, "ExtractionService", StoredEvidenceService)
    report = await v7.evaluate_sealed_holdout(
        sealed, manifest, provider="openai",
        execution_binding={"provider": "openai", "model": "test-model", "runtime_fingerprint_sha256": "f" * 64},
    )
    report["cases"][0]["provider_receipt"]["response_id"] = "resp_fabricated"
    result_path.write_text(json.dumps(report), encoding="utf-8")
    client = _mock_client(missing=True)
    try:
        with pytest.raises(HoldoutError, match="provider retrieval failed"):
            await verify_v7_provider_evidence(
                result_path, sealed, manifest, require_trusted_runtime=False, api_key="test", client=client
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_live_provider_retrieval_rejects_wrong_stored_input(tmp_path, monkeypatch):
    StoredEvidenceService.responses = {}
    sealed, manifest, result_path = _fixture(tmp_path)
    monkeypatch.setattr(v7, "ExtractionService", StoredEvidenceService)
    report = await v7.evaluate_sealed_holdout(
        sealed, manifest, provider="openai",
        execution_binding={"provider": "openai", "model": "test-model", "runtime_fingerprint_sha256": "f" * 64},
    )
    result_path.write_text(json.dumps(report), encoding="utf-8")
    client = _mock_client(tamper_input=True)
    try:
        with pytest.raises(HoldoutError, match="user input differs"):
            await verify_v7_provider_evidence(
                result_path, sealed, manifest, require_trusted_runtime=False, api_key="test", client=client
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_live_provider_retrieval_rejects_tampered_remote_output(tmp_path, monkeypatch):
    StoredEvidenceService.responses = {}
    sealed, manifest, result_path = _fixture(tmp_path)
    monkeypatch.setattr(v7, "ExtractionService", StoredEvidenceService)
    report = await v7.evaluate_sealed_holdout(
        sealed, manifest, provider="openai",
        execution_binding={"provider": "openai", "model": "test-model", "runtime_fingerprint_sha256": "f" * 64},
    )
    result_path.write_text(json.dumps(report), encoding="utf-8")
    client = _mock_client(tamper_output=True)
    try:
        with pytest.raises(HoldoutError, match="output hash differs"):
            await verify_v7_provider_evidence(
                result_path, sealed, manifest, require_trusted_runtime=False, api_key="test", client=client
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_live_provider_retrieval_rejects_wrong_stored_system_prompt(tmp_path, monkeypatch):
    StoredEvidenceService.responses = {}
    sealed, manifest, result_path = _fixture(tmp_path)
    monkeypatch.setattr(v7, "ExtractionService", StoredEvidenceService)
    report = await v7.evaluate_sealed_holdout(
        sealed, manifest, provider="openai",
        execution_binding={"provider": "openai", "model": "test-model", "runtime_fingerprint_sha256": "f" * 64},
    )
    result_path.write_text(json.dumps(report), encoding="utf-8")
    client = _mock_client(tamper_prompt=True)
    try:
        with pytest.raises(HoldoutError, match="system prompt differs"):
            await verify_v7_provider_evidence(
                result_path, sealed, manifest, require_trusted_runtime=False, api_key="test", client=client
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_live_provider_retrieval_rejects_remote_metadata_mismatch(tmp_path, monkeypatch):
    StoredEvidenceService.responses = {}
    sealed, manifest, result_path = _fixture(tmp_path)
    monkeypatch.setattr(v7, "ExtractionService", StoredEvidenceService)
    report = await v7.evaluate_sealed_holdout(
        sealed, manifest, provider="openai",
        execution_binding={"provider": "openai", "model": "test-model", "runtime_fingerprint_sha256": "f" * 64},
    )
    result_path.write_text(json.dumps(report), encoding="utf-8")
    client = _mock_client(tamper_metadata=True)
    try:
        with pytest.raises(HoldoutError, match="metadata differs"):
            await verify_v7_provider_evidence(
                result_path, sealed, manifest, require_trusted_runtime=False, api_key="test", client=client
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_offline_replay_rejects_nonstored_provider_receipt(tmp_path, monkeypatch):
    StoredEvidenceService.responses = {}
    sealed, manifest, result_path = _fixture(tmp_path)
    monkeypatch.setattr(v7, "ExtractionService", StoredEvidenceService)
    report = await v7.evaluate_sealed_holdout(
        sealed, manifest, provider="openai",
        execution_binding={"provider": "openai", "model": "test-model", "runtime_fingerprint_sha256": "f" * 64},
    )
    report["cases"][0]["provider_receipt"]["stored"] = False
    # Keep local aggregate metrics/gate self-consistent so the receipt check is the failing boundary.
    report["metrics"]["missing_stored_provider_receipt_cases"] = 1
    report["gate"] = v7.evaluate_v7_gate(report["metrics"])
    result_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(HoldoutError, match="was not stored"):
        verify_v7_evidence(result_path, sealed, manifest, require_trusted_runtime=False)


def test_v7_storage_config_is_code_owned_without_forcing_storage_on_ordinary_extraction():
    from signallock.providers.openai_http import extraction_provider_config, v7_provider_config
    from signallock.evaluation.holdout import _runtime_binding, verify_v7_runtime_binding

    assert extraction_provider_config() == {"store": False}
    assert v7_provider_config() == {"store": True}
    good = _runtime_binding(provider="openai", model="test-model", provider_config={"store": True})
    verify_v7_runtime_binding({"strict_v7": True, "runtime_binding": good}, provider="openai", model="test-model")
    bad = _runtime_binding(provider="openai", model="test-model", provider_config={"store": False})
    with pytest.raises(HoldoutError, match="provider_config"):
        verify_v7_runtime_binding({"strict_v7": True, "runtime_binding": bad}, provider="openai", model="test-model")
