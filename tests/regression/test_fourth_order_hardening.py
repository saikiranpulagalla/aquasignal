from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from signallock.contracts.extractor import HeuristicExtractor
from signallock.contracts.schema import Action, ActionType, EvidenceSpan, Modality, SafetyContract
from signallock.evaluation import v7
from signallock.evaluation.holdout import (
    HoldoutError,
    _identity_key as holdout_identity_key,
    _runtime_binding,
    seal_holdout,
    validate_v7_quality,
    verify_v7_runtime_binding,
)
from signallock.evaluation.review_workflow import (
    _identity_key as review_identity_key,
    _mapping_sha256,
    _write_jsonl,
    finalize_reviewed_holdout,
    make_blind_review_templates,
)
from signallock.evaluation.v7_evidence import verify_v7_evidence
from signallock.providers.openai_http import (
    OpenAIResponsesProvider,
    ProviderError,
    _native_semantic_guard,
    contract_from_provider_output,
)
from signallock.verification.engine import VerificationEngine


SOURCE = "Residents must shelter indoors."
SOURCE_CONTRACT = HeuristicExtractor().extract(SOURCE, source_id="authority")


def _raw_contract(contract: SafetyContract) -> str:
    return json.dumps(contract.model_dump(mode="json"), ensure_ascii=False)


@pytest.mark.parametrize(
    "language,text,kind,verb,obj",
    [
        ("hi", "निकासी न करें।", ActionType.EVACUATE, "evacuate", None),
        ("te", "బయటకు వెళ్లవద్దు.", ActionType.EVACUATE, "evacuate", None),
        ("hi", "पानी न पिएं।", ActionType.EXECUTE, "drink", "water"),
        ("te", "నీటిని తాగవద్దు.", ActionType.EXECUTE, "drink", "water"),
    ],
)
def test_general_native_negation_cannot_survive_as_positive_required_action(language, text, kind, verb, obj):
    ev = EvidenceSpan(quote=text, start_char=0, end_char=len(text))
    wrong = SafetyContract(
        language=language,
        required_actions=[Action(type=kind, verb=verb, object=obj, modality=Modality.MUST, evidence=ev)],
    )
    findings = _native_semantic_guard(text, wrong)
    assert findings
    assert any("negative" in item or "PROHIBITED" in item for item in findings)

    replayed = contract_from_provider_output(_raw_contract(wrong), text, language=language, source_id="candidate")
    assert replayed.unresolved_operational_text

    src_text = "Evacuate." if kind == ActionType.EVACUATE else "Drink water."
    src_ev = EvidenceSpan(quote=src_text, start_char=0, end_char=len(src_text))
    source = SafetyContract(
        language="en",
        required_actions=[Action(type=kind, verb=verb, object=obj, modality=Modality.MUST, evidence=src_ev)],
    )
    assert VerificationEngine().verify(source, replayed).decision.value != "PASS"


@pytest.mark.asyncio
async def test_qualification_evidence_refuses_missing_provider_model_identity():
    contract = HeuristicExtractor().extract("Evacuate now.", source_id="c")

    class MissingModel(OpenAIResponsesProvider):
        async def _request(self, payload):
            return {"id": "resp-1", "output_text": _raw_contract(contract), "usage": {}}

    with pytest.raises(ProviderError, match="model identity"):
        await MissingModel(api_key="x", model="frozen-model").extract_contract_with_evidence(
            "Evacuate now.", language="en", source_id="c"
        )



def test_runtime_binding_rejects_manifest_supplied_forged_provider_config():
    forged = _runtime_binding(
        provider="openai",
        model="frozen-model",
        provider_config={"store": True, "temperature": 2.0, "made_up": "accepted"},
    )
    with pytest.raises(HoldoutError, match="provider_config"):
        verify_v7_runtime_binding(
            {"strict_v7": True, "runtime_binding": forged},
            provider="openai",
            model="frozen-model",
        )


class ReplayableEvidenceService:
    def __init__(self, provider):
        self.provider = provider

    async def extract_with_evidence(self, text, *, language="en", source_id=None, audit_metadata=None, store=False):
        base = HeuristicExtractor().extract(text, language=language, source_id=source_id)
        raw = _raw_contract(base)
        contract = contract_from_provider_output(raw, text, language=language, source_id=source_id)
        return contract, {
            "response_id": f"resp-{source_id}",
            "response_model": "test-model",
            "response_created_at": 1,
            "response_completed_at": 2,
            "response_status": "completed",
            "stored": bool(store),
            "response_metadata": dict(audit_metadata or {}),
            "usage": {},
            "raw_output_text": raw,
            "output_text_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        }


@pytest.mark.asyncio
async def test_checkpoint_recovery_flag_cannot_be_flipped_to_fresh(tmp_path, monkeypatch):
    row = {
        "case_id": "c1",
        "source_text": SOURCE,
        "source_language": "en",
        "source_contract": SOURCE_CONTRACT.model_dump(mode="json"),
        "candidate_text": SOURCE,
        "candidate_language": "en",
        "expected_decision": "PASS",
        "human_reviewed": True,
        "fault_class": "clean",
    }
    src, sealed, manifest, checkpoint, result = (
        tmp_path / "in.jsonl",
        tmp_path / "sealed.jsonl",
        tmp_path / "manifest.json",
        tmp_path / "checkpoint.json",
        tmp_path / "result.json",
    )
    src.write_text(json.dumps(row) + "\n", encoding="utf-8")
    seal_holdout(src, sealed, manifest, schema_version="1", verifier_version="v", extractor_version="e", prompt_version="p")
    monkeypatch.setattr(v7, "ExtractionService", ReplayableEvidenceService)
    binding = {"provider": "openai", "model": "test-model"}
    first = await v7.evaluate_sealed_holdout(
        sealed, manifest, provider="openai", checkpoint_path=checkpoint, execution_binding=binding
    )
    resumed = await v7.evaluate_sealed_holdout(
        sealed, manifest, provider="openai", checkpoint_path=checkpoint,
        execution_binding=binding, allow_checkpoint_recovery=True,
    )
    assert first["run_id"] != resumed["run_id"]
    assert resumed["cases"][0]["origin_run_id"] == first["run_id"]
    assert resumed["metrics"]["checkpoint_recovered_cases"] == 1

    resumed["cases"][0]["recovered_from_checkpoint"] = False
    rr = v7.V7CaseResult(**resumed["cases"][0])
    resumed["metrics"] = v7.compute_v7_metrics([rr], quality=resumed["manifest"].get("quality") or {})
    resumed["gate"] = v7.evaluate_v7_gate(resumed["metrics"])
    result.write_text(json.dumps(resumed), encoding="utf-8")
    with pytest.raises(HoldoutError, match="claims fresh execution"):
        verify_v7_evidence(result, sealed, manifest, require_trusted_runtime=False)


class WrongContractEvidenceService:
    def __init__(self, provider):
        self.provider = provider

    async def extract_with_evidence(self, text, *, language="en", source_id=None, audit_metadata=None, store=False):
        ev = EvidenceSpan(quote=text, start_char=0, end_char=len(text))
        wrong = SafetyContract(
            language=language,
            required_actions=[Action(type=ActionType.EVACUATE, verb="evacuate", object="indoors", modality=Modality.MUST, evidence=ev)],
            source_id=source_id,
        )
        raw = _raw_contract(wrong)
        contract = contract_from_provider_output(raw, text, language=language, source_id=source_id)
        return contract, {
            "response_id": "resp-original",
            "response_model": "m",
            "response_created_at": 1,
            "response_completed_at": 2,
            "response_status": "completed",
            "stored": bool(store),
            "response_metadata": dict(audit_metadata or {}),
            "usage": {},
            "raw_output_text": raw,
            "output_text_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        }


@pytest.mark.asyncio
async def test_candidate_contract_cannot_be_detached_from_provider_raw_output(tmp_path, monkeypatch):
    row = {
        "case_id": "c",
        "source_text": SOURCE,
        "source_language": "en",
        "source_contract": SOURCE_CONTRACT.model_dump(mode="json"),
        "candidate_text": SOURCE,
        "candidate_language": "en",
        "expected_decision": "PASS",
        "human_reviewed": True,
        "fault_class": "clean",
    }
    src, sealed, manifest, result = tmp_path / "i", tmp_path / "s", tmp_path / "m", tmp_path / "r"
    src.write_text(json.dumps(row) + "\n", encoding="utf-8")
    seal_holdout(src, sealed, manifest, schema_version="1", verifier_version="v", extractor_version="e", prompt_version="p")
    monkeypatch.setattr(v7, "ExtractionService", WrongContractEvidenceService)
    report = await v7.evaluate_sealed_holdout(
        sealed, manifest, provider="openai", execution_binding={"provider": "openai", "model": "m"}
    )
    assert report["cases"][0]["actual_decision"] == "BLOCK"

    good = SOURCE_CONTRACT.model_copy(update={"source_id": "v7-candidate:c"}).model_dump(mode="json")
    report["cases"][0]["candidate_contract"] = good
    report["cases"][0]["candidate_contract_sha256"] = v7._canonical_sha256(good)
    verdict = VerificationEngine().verify(SOURCE_CONTRACT, SafetyContract.model_validate(good))
    report["cases"][0]["actual_decision"] = verdict.decision.value
    report["cases"][0]["exact_match"] = True
    report["cases"][0]["critical_failures"] = list(verdict.critical_failures)
    report["cases"][0]["warnings"] = list(verdict.warnings)
    rr = v7.V7CaseResult(**report["cases"][0])
    report["metrics"] = v7.compute_v7_metrics([rr], quality=report["manifest"].get("quality") or {})
    report["gate"] = v7.evaluate_v7_gate(report["metrics"])
    result.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(HoldoutError, match="does not reconstruct saved candidate contract"):
        verify_v7_evidence(result, sealed, manifest, require_trusted_runtime=False)


FAULTS = ["action_area", "action_audience", "quantity_exception_binding", "modality", "temporal", "logic_sequence"]


def _authored_rows() -> list[dict]:
    rows = []
    for lang in ("hi", "te"):
        for i in range(12):
            src = f"Evacuate sector {lang}-{i} now."
            sc = HeuristicExtractor().extract(src, language="en", source_id=f"authority-{lang}-{i}")
            clean = i < 6
            target = "PASS" if clean else "BLOCK"
            fault = "clean" if clean else FAULTS[i - 6]
            cand = f"निवासी तुरंत सलाह का पालन करें {i}" if lang == "hi" else f"నివాసితులు వెంటనే సలహా పాటించండి {i}"
            rows.append({
                "task_id": f"{lang}-{i}", "source_seed_id": f"seed-{lang}-{i}",
                "source_text": src, "source_language": "en", "source_reference": f"ref-{lang}-{i}",
                "candidate_language": lang, "target_decision": target, "fault_class": fault,
                "authoring_instruction": "x", "candidate_text": cand,
                "author_id": "author-hi" if lang == "hi" else "author-te",
                "source_contract": sc.model_dump(mode="json"),
                "authority_reviewer_id": "authority-reviewer", "authority_reviewed_at": "2026-09-12T10:00:00+00:00",
                "authority_notes": "",
            })
    return rows


def test_review_mapping_task_reassociation_is_rejected_even_if_mapping_hash_is_recomputed(tmp_path):
    authored = _authored_rows()
    primary, secondary, mapping = make_blind_review_templates(authored)
    for role, sheet, reviewer in (("primary", primary, "reviewer-p"), ("secondary", secondary, "reviewer-s")):
        for r in sheet:
            task = mapping[role][r["review_id"]]["task_id"]
            target = next(x["target_decision"] for x in authored if x["task_id"] == task)
            r.update(reviewer_id=reviewer, reviewed_at="2026-09-12T11:00:00+00:00", verdict=target, notes="")

    role = "primary"
    ids = list(mapping[role])
    a, b = ids[0], ids[1]
    mapping[role][a]["task_id"], mapping[role][b]["task_id"] = mapping[role][b]["task_id"], mapping[role][a]["task_id"]
    mapping["mapping_sha256"] = _mapping_sha256(mapping)

    a_path, p_path, s_path, m_path = tmp_path / "a", tmp_path / "p", tmp_path / "s", tmp_path / "m"
    _write_jsonl(a_path, authored); _write_jsonl(p_path, primary); _write_jsonl(s_path, secondary)
    m_path.write_text(json.dumps(mapping), encoding="utf-8")
    with pytest.raises(HoldoutError, match="content is not bound|task binding mismatch"):
        finalize_reviewed_holdout(a_path, p_path, s_path, m_path)



def _quality_rows(*, source_language="en", numeric_clone=False) -> list[dict]:
    rows = []
    for lang in ("hi", "te"):
        for i in range(12):
            src = f"Evacuate zone {i + 1}." if numeric_clone else f"Evacuate distinct {lang} sector {i + 1} immediately because marker {chr(65+i)} applies."
            sc = HeuristicExtractor().extract(src, language="en", source_id=f"authority-{lang}-{i}").model_copy(update={"language": source_language})
            clean = i < 6
            decision = "PASS" if clean else "BLOCK"
            fault = "clean" if clean else FAULTS[i - 6]
            cand = f"निवासी तुरंत सलाह का पालन करें {i + 1}" if lang == "hi" else f"నివాసితులు వెంటనే సలహా పాటించండి {i + 1}"
            row = {
                "case_id": f"{lang}-{i}", "source_text": src, "source_language": source_language,
                "source_contract": sc.model_dump(mode="json"), "candidate_text": cand, "candidate_language": lang,
                "expected_decision": decision, "human_reviewed": True,
                "reviewer_id": "reviewer-P", "reviewed_at": "2026-09-12T12:00:00+00:00",
                "source_reference": f"ref-{lang}-{i}", "fault_class": fault,
                "author_id": "author-A" if lang == "hi" else "author-B",
                "authority_reviewer_id": "authority-X", "authority_reviewed_at": "2026-09-12T11:00:00+00:00",
            }
            if decision == "BLOCK":
                row.update(second_reviewer_id="reviewer-S", second_reviewed_at="2026-09-12T12:05:00+00:00")
            rows.append(row)
    return rows


def test_v7_quality_requires_english_authority_source_and_rejects_numeric_clone_families():
    with pytest.raises(HoldoutError, match="source_language must be English"):
        validate_v7_quality(_quality_rows(source_language="fr"))
    with pytest.raises(HoldoutError, match="source families"):
        validate_v7_quality(_quality_rows(numeric_clone=True))



def test_identity_canonicalization_removes_zero_width_aliases():
    a = "reviewer-alpha"
    b = "reviewer-\u200balpha"
    assert holdout_identity_key(a) == holdout_identity_key(b)
    assert review_identity_key(a) == review_identity_key(b)



def test_public_live_session_cookie_is_short_lived_capability_not_master_token(monkeypatch):
    import apps.api.main as api

    monkeypatch.setattr(api, "_LIVE_PROVIDER_TOKEN", "MASTER-DEMO-TOKEN")
    monkeypatch.setattr(api, "_AUTHORITY_SECRET_CONFIGURED", True)
    api._LIVE_SESSIONS.clear()
    client = TestClient(api.app)
    response = client.post("/api/live-session", headers={"X-SignalLock-Demo-Token": "MASTER-DEMO-TOKEN"})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "MASTER-DEMO-TOKEN" not in cookie
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "Max-Age=900" in cookie
    assert api._LIVE_SESSIONS



def test_api_version_comes_from_pyproject_single_source():
    import tomllib
    import apps.api.main as api

    root = Path(api.__file__).resolve().parents[2]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert api.app.version == project["project"]["version"]


def test_private_v7_workflow_artifacts_are_ignored_by_default():
    root = Path(__file__).resolve().parents[2]
    ignored = {line.strip() for line in (root / ".gitignore").read_text(encoding="utf-8").splitlines()}
    required = {
        "data/multilingual/v7_blind_review_map.json",
        "data/multilingual/v7_authoring_packet_with_authority_drafts.jsonl",
        "data/multilingual/v7_review_draft.jsonl",
        "data/multilingual/v7_authored.jsonl",
        "data/multilingual/v7_primary_review.jsonl",
        "data/multilingual/v7_secondary_review.jsonl",
        "data/multilingual/v7_reviewed.jsonl",
    }
    assert required <= ignored
