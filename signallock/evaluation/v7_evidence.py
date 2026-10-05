from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from signallock.contracts.provenance import validate_provenance
from signallock.contracts.schema import SafetyContract
from signallock.evaluation.holdout import (
    HoldoutError,
    load_jsonl,
    sha256_file,
    validate_v7_quality,
    verify_code_binding,
    verify_seal,
    verify_v7_runtime_binding,
)
from signallock.evaluation.release import resolve_release_identity
from signallock.evaluation.environment import require_qualification_environment
from signallock.evaluation.v7 import (
    V7CaseResult,
    _canonical_sha256,
    compute_v7_metrics,
    evaluate_v7_gate,
    provider_audit_metadata,
)
from signallock.providers.openai_http import ProviderError, contract_from_provider_output
from signallock.verification.engine import VerificationEngine


def _load_result(path: Path) -> dict:
    if not path.exists():
        raise HoldoutError(f"V7 result does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HoldoutError(f"invalid V7 result JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HoldoutError("V7 result must be a JSON object")
    return payload


def verify_v7_evidence(
    result_path: Path,
    holdout_path: Path,
    manifest_path: Path,
    *,
    root: Path | None = None,
    require_trusted_runtime: bool = True,
) -> dict:
    """Replay a V7 result from sealed inputs and stored candidate contracts.

    This proves internal evidence integrity by reconstructing the candidate contract from
    the retained raw provider structured output, then replaying the frozen verifier against
    the sealed source contract. Provider receipts remain audit metadata rather than a
    cryptographic attestation by the external provider.
    """
    manifest = verify_seal(holdout_path, manifest_path)
    rows = load_jsonl(holdout_path)
    rows_by_id = {str(row["case_id"]): row for row in rows}
    if len(rows_by_id) != len(rows):
        raise HoldoutError("sealed V7 holdout contains duplicate case IDs")

    report = _load_result(result_path)
    if report.get("manifest_sha256") != manifest.get("sha256"):
        raise HoldoutError("V7 result is bound to a different sealed holdout")
    if _canonical_sha256(report.get("manifest")) != _canonical_sha256(manifest):
        raise HoldoutError("embedded V7 manifest differs from the sealed manifest")

    execution_binding = report.get("execution_binding") or {}
    saved_provider = str(report.get("provider") or "").strip()
    saved_model = str(report.get("model") or execution_binding.get("model") or "").strip()
    if not saved_provider or not saved_model:
        raise HoldoutError("V7 result is missing frozen provider/model identity")
    if execution_binding.get("provider") not in {None, saved_provider}:
        raise HoldoutError("V7 result provider differs from its execution binding")
    if execution_binding.get("model") not in {None, saved_model}:
        raise HoldoutError("V7 result model differs from its execution binding")

    run_id = str(report.get("run_id") or "").strip()
    run_started_at_utc = str(report.get("run_started_at_utc") or "").strip()
    if not run_id or not run_started_at_utc:
        raise HoldoutError("V7 result is missing run_id/run_started_at_utc freshness evidence")
    try:
        run_started = datetime.fromisoformat(run_started_at_utc.replace("Z", "+00:00"))
        if run_started.tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise HoldoutError("V7 result run_started_at_utc must be timezone-aware ISO-8601") from exc

    # Production replay never trusts the manifest's claimed quality block.  Recompute
    # it from the exact sealed rows and require the strict V7 sealer/runtime binding.
    # Generic manifests remain usable only by low-level tests that do not provide a
    # runtime root and explicitly disable trusted-runtime enforcement.
    production_replay = root is not None or require_trusted_runtime
    if production_replay:
        if manifest.get("strict_v7") is not True:
            raise HoldoutError("V7 replay requires a strict V7 manifest")
        recomputed_quality = validate_v7_quality(rows)
        if _canonical_sha256(recomputed_quality) != _canonical_sha256(manifest.get("quality")):
            raise HoldoutError("V7 manifest quality block does not match quality recomputed from sealed rows")
        verify_v7_runtime_binding(manifest, provider=saved_provider, model=saved_model)
        require_qualification_environment()
        if execution_binding.get("environment_sha256") != manifest["runtime_binding"].get("environment_sha256"):
            raise HoldoutError("V7 replay environment binding is missing or mismatched")
    else:
        recomputed_quality = manifest.get("quality") or {}

    current_identity = None
    if root is not None:
        current_identity = resolve_release_identity(root)
        if require_trusted_runtime and (not current_identity.get("clean") or not current_identity.get("identity")):
            raise HoldoutError(current_identity.get("error") or "runtime is not externally trusted")
        if production_replay and current_identity.get("identity"):
            verify_code_binding(manifest, current_identity["identity"])
        saved_runtime = report.get("runtime_identity") or {}
        saved_tree = (
            saved_runtime.get("runtime_tree_sha256")
            or execution_binding.get("runtime_tree_sha256")
        )
        if saved_tree and saved_tree != current_identity.get("runtime_tree_sha256"):
            raise HoldoutError("V7 result runtime tree hash does not match the replay runtime")
        saved_identity = saved_runtime.get("identity") or execution_binding.get("runtime_identity")
        if saved_identity and current_identity.get("identity") and saved_identity != current_identity.get("identity"):
            raise HoldoutError("V7 result immutable runtime identity does not match the replay runtime")

    raw_cases = report.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != len(rows):
        raise HoldoutError("V7 result case coverage does not match the sealed holdout")

    results: list[V7CaseResult] = []
    seen: set[str] = set()
    replayed = 0
    provider_receipts = 0
    provider_response_ids: set[str] = set()
    verifier = VerificationEngine()

    for raw in raw_cases:
        try:
            result = V7CaseResult(**raw)
        except Exception as exc:
            raise HoldoutError(f"malformed V7 case result: {exc}") from exc
        if result.case_id in seen:
            raise HoldoutError(f"duplicate V7 result case_id {result.case_id!r}")
        seen.add(result.case_id)
        row = rows_by_id.get(result.case_id)
        if row is None:
            raise HoldoutError(f"unknown V7 result case_id {result.case_id!r}")

        expected_metadata = {
            "source_language": row["source_language"],
            "candidate_language": row["candidate_language"],
            "fault_class": str(row.get("fault_class", "unclassified")).casefold(),
            "expected_decision": row["expected_decision"],
        }
        for key, expected in expected_metadata.items():
            if getattr(result, key) != expected:
                raise HoldoutError(f"{result.case_id}: result {key} differs from sealed holdout")

        origin_run_id = str(result.origin_run_id or "").strip()
        executed_in_run_id = str(result.executed_in_run_id or "").strip()
        if not origin_run_id or not executed_in_run_id:
            raise HoldoutError(f"{result.case_id}: missing case run-origin evidence")
        if result.recovered_from_checkpoint:
            if origin_run_id == run_id and executed_in_run_id == run_id:
                raise HoldoutError(f"{result.case_id}: recovered flag is inconsistent with same-run origin evidence")
        elif origin_run_id != run_id or executed_in_run_id != run_id:
            raise HoldoutError(
                f"{result.case_id}: case claims fresh execution but origin/executed run IDs differ from current run"
            )

        if result.provider_error is not None:
            if result.actual_decision != "REVIEW":
                raise HoldoutError(f"{result.case_id}: provider-error case must be REVIEW")
            if result.candidate_contract is not None or result.candidate_contract_sha256 is not None:
                raise HoldoutError(f"{result.case_id}: provider-error case must not contain candidate-contract evidence")
            if result.provider_receipt is not None:
                raise HoldoutError(f"{result.case_id}: failed provider case must not claim a successful provider receipt")
            if result.exact_match != (row["expected_decision"] == "REVIEW"):
                raise HoldoutError(f"{result.case_id}: exact_match is inconsistent")
            results.append(result)
            continue

        if not isinstance(result.candidate_contract, dict):
            raise HoldoutError(f"{result.case_id}: successful case is missing replayable candidate contract")
        if result.candidate_contract_sha256 != _canonical_sha256(result.candidate_contract):
            raise HoldoutError(f"{result.case_id}: candidate-contract hash mismatch")
        if not isinstance(result.provider_receipt, dict) or not str(result.provider_receipt.get("response_id", "")).strip():
            raise HoldoutError(f"{result.case_id}: successful live case is missing provider response receipt")
        response_id = str(result.provider_receipt.get("response_id", "")).strip()
        if response_id in provider_response_ids:
            raise HoldoutError(f"{result.case_id}: provider response_id is reused across V7 cases")
        provider_response_ids.add(response_id)
        response_model = str(result.provider_receipt.get("response_model", "")).strip()
        if response_model != saved_model:
            raise HoldoutError(
                f"{result.case_id}: provider receipt model {response_model!r} differs from frozen model {saved_model!r}"
            )
        output_hash = str(result.provider_receipt.get("output_text_sha256", "")).strip().casefold()
        if len(output_hash) != 64 or any(ch not in "0123456789abcdef" for ch in output_hash):
            raise HoldoutError(f"{result.case_id}: provider output_text_sha256 is malformed")
        if result.provider_receipt.get("stored") is not True:
            raise HoldoutError(f"{result.case_id}: V7 provider response was not stored for independent retrieval")
        if result.provider_receipt.get("response_status") != "completed":
            raise HoldoutError(f"{result.case_id}: provider response status is not completed")
        created_at = result.provider_receipt.get("response_created_at")
        if not isinstance(created_at, (int, float)) or created_at <= 0:
            raise HoldoutError(f"{result.case_id}: provider response_created_at is missing or invalid")
        expected_provider_metadata = provider_audit_metadata(
            row, run_id=run_id, manifest_sha256=manifest["sha256"], execution_binding=execution_binding
        )
        if result.provider_receipt.get("response_metadata") != expected_provider_metadata:
            raise HoldoutError(f"{result.case_id}: provider response metadata does not match V7 case binding")
        raw_output_text = result.provider_receipt.get("raw_output_text")
        if not isinstance(raw_output_text, str) or not raw_output_text.strip():
            raise HoldoutError(f"{result.case_id}: provider receipt is missing replayable raw_output_text")
        actual_output_hash = hashlib.sha256(raw_output_text.encode("utf-8")).hexdigest()
        if actual_output_hash != output_hash:
            raise HoldoutError(f"{result.case_id}: provider raw output hash mismatch")
        provider_receipts += 1

        try:
            source_contract = SafetyContract.model_validate(row["source_contract"])
            expected_source_id = f"v7-candidate:{result.case_id}"
            candidate_contract = contract_from_provider_output(
                raw_output_text,
                row["candidate_text"],
                language=row["candidate_language"],
                source_id=expected_source_id,
            )
        except (ProviderError, Exception) as exc:
            raise HoldoutError(f"{result.case_id}: provider output could not be deterministically replayed: {exc}") from exc
        replay_payload = candidate_contract.model_dump(mode="json")
        if _canonical_sha256(replay_payload) != result.candidate_contract_sha256:
            raise HoldoutError(f"{result.case_id}: retained provider output does not reconstruct saved candidate contract")
        if _canonical_sha256(replay_payload) != _canonical_sha256(result.candidate_contract):
            raise HoldoutError(f"{result.case_id}: saved candidate contract differs from provider-output replay")
        if candidate_contract.language != row["candidate_language"]:
            raise HoldoutError(f"{result.case_id}: candidate contract language differs from sealed candidate language")
        if candidate_contract.source_id != expected_source_id:
            raise HoldoutError(f"{result.case_id}: candidate contract source_id is not the V7 case binding")
        provenance_errors = validate_provenance(row["candidate_text"], candidate_contract, require_p0=True)
        if provenance_errors:
            raise HoldoutError(f"{result.case_id}: replay candidate provenance invalid: {'; '.join(provenance_errors)}")

        verdict = verifier.verify(source_contract, candidate_contract)
        if result.actual_decision != verdict.decision.value:
            raise HoldoutError(f"{result.case_id}: saved decision does not replay from stored candidate contract")
        if result.exact_match != (verdict.decision.value == row["expected_decision"]):
            raise HoldoutError(f"{result.case_id}: exact_match does not replay")
        if list(result.critical_failures) != list(verdict.critical_failures):
            raise HoldoutError(f"{result.case_id}: saved critical failures do not replay")
        if list(result.warnings) != list(verdict.warnings):
            raise HoldoutError(f"{result.case_id}: saved warnings do not replay")
        replayed += 1
        results.append(result)

    if seen != set(rows_by_id):
        raise HoldoutError("V7 result does not cover exactly the sealed case IDs")

    recomputed_metrics = compute_v7_metrics(results, quality=recomputed_quality)
    if _canonical_sha256(recomputed_metrics) != _canonical_sha256(report.get("metrics")):
        raise HoldoutError("saved V7 metrics do not match metrics recomputed from case evidence")
    recomputed_gate = evaluate_v7_gate(recomputed_metrics)
    if _canonical_sha256(recomputed_gate) != _canonical_sha256(report.get("gate")):
        raise HoldoutError("saved V7 gate does not match the recomputed gate")

    return {
        "kind": "SignalLock V7 replay verification",
        "version": "2.0",
        "verified": True,
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "result_sha256": sha256_file(result_path),
        "sealed_holdout_sha256": manifest["sha256"],
        "manifest_file_sha256": sha256_file(manifest_path),
        "run_id": run_id,
        "run_started_at_utc": run_started_at_utc,
        "resumed_from_run_id": report.get("resumed_from_run_id"),
        "provider": report.get("provider"),
        "model": report.get("model") or (report.get("execution_binding") or {}).get("model"),
        "replayed_successful_cases": replayed,
        "provider_receipt_cases": provider_receipts,
        "provider_error_cases": recomputed_metrics["provider_error_cases"],
        "checkpoint_recovered_cases": recomputed_metrics["checkpoint_recovered_cases"],
        "gate": recomputed_gate,
        "runtime_identity": current_identity,
        "limitation": "Provider response receipts are audit metadata, not a cryptographic attestation by the external provider.",
    }
