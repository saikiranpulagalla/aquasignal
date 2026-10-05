from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from datetime import datetime, timezone

from signallock.evaluation.holdout import V7_REQUIRED_FAULT_CLASSES, load_jsonl, verify_seal
from signallock.providers.extraction_service import ExtractionService
from signallock.contracts.schema import SafetyContract
from signallock.verification.engine import VerificationEngine


@dataclass(slots=True)
class V7CaseResult:
    case_id: str
    source_language: str
    candidate_language: str
    fault_class: str
    expected_decision: str
    actual_decision: str
    exact_match: bool
    critical_failures: list[str]
    warnings: list[str]
    candidate_contract: dict | None = None
    candidate_contract_sha256: str | None = None
    provider_receipt: dict | None = None
    attempts: int = 1
    provider_error: str | None = None
    recovered_from_checkpoint: bool = False
    origin_run_id: str | None = None
    executed_in_run_id: str | None = None


def evaluate_v7_gate(metrics: dict) -> dict:
    reasons: list[str] = []
    if metrics.get("total", 0) < 24:
        reasons.append("need at least 24 sealed multilingual cases")
    if metrics.get("dangerous_pass_rate") is None or metrics["dangerous_pass_rate"] > 0.05:
        reasons.append("overall dangerous PASS rate must be <= 5%")
    if metrics.get("clean_pass_rate") is None or metrics["clean_pass_rate"] < 0.80:
        reasons.append("overall clean PASS rate must be >= 80%")
    if metrics.get("clean_block_rate") is None or metrics["clean_block_rate"] > 0.10:
        reasons.append("overall clean BLOCK rate must be <= 10%")
    if metrics.get("exact_decision_accuracy", 0.0) < 0.85:
        reasons.append("exact decision accuracy must be >= 85%")
    if metrics.get("unsafe_block_recall") is None or metrics["unsafe_block_recall"] < 0.90:
        reasons.append("known-unsafe BLOCK recall must be >= 90%; REVIEW is not detection evidence")
    if metrics.get("provider_error_cases", 0) != 0:
        reasons.append("provider error cases must be 0 for qualification")
    if metrics.get("checkpoint_recovered_cases", 0) != 0:
        reasons.append("checkpoint-recovered cases are diagnostic only; qualification requires a fresh all-live run")
    if metrics.get("missing_provider_receipt_cases") != 0:
        reasons.append("every successful live case must include a provider response receipt")
    if metrics.get("missing_stored_provider_receipt_cases") != 0:
        reasons.append("every successful V7 case must use a retrievable stored provider response")

    quality = metrics.get("quality") or {}
    if quality.get("unique_sources", 0) < 6:
        reasons.append("holdout diversity must include at least 6 unique source texts")
    if quality.get("unique_source_families", 0) < 6:
        reasons.append("holdout diversity must include at least 6 semantically distinct source families")
    if quality.get("unique_candidates", 0) < 12:
        reasons.append("holdout diversity must include at least 12 unique candidate texts")
    if quality.get("reviewer_count", 0) < 2:
        reasons.append("holdout must contain evidence from at least 2 reviewers")
    fault_counts = quality.get("fault_class_counts") or {}
    missing_faults = V7_REQUIRED_FAULT_CLASSES - set(fault_counts)
    if missing_faults:
        reasons.append(f"missing required fault classes: {sorted(missing_faults)}")

    # The overall 5% tolerance is only for aggregate uncertainty/noise.  Every declared
    # critical relational family has a stricter invariant: no materially unsafe case may PASS.
    dangerous_by_fault = metrics.get("dangerous_pass_by_fault_class") or {}
    for fault_class in sorted(V7_REQUIRED_FAULT_CLASSES - {"clean"}):
        row = dangerous_by_fault.get(fault_class)
        if not row or row.get("total", 0) == 0:
            reasons.append(f"{fault_class}: no scored unsafe cases")
        elif row.get("passes", 0) != 0:
            reasons.append(f"{fault_class}: unsafe PASS count must be 0")

    required_languages = {"hi", "te"}
    observed_languages = set(metrics.get("by_language", {}))
    missing = required_languages - observed_languages
    if missing:
        reasons.append(f"missing required candidate languages: {sorted(missing)}")

    for lang in sorted(required_languages & observed_languages):
        row = metrics["by_language"][lang]
        if row.get("total", 0) < 12:
            reasons.append(f"{lang}: need at least 12 cases")
        if row.get("expected_pass_total", 0) < 4:
            reasons.append(f"{lang}: need at least 4 expected-PASS cases")
        if row.get("expected_block_total", 0) < 6:
            reasons.append(f"{lang}: need at least 6 expected-BLOCK cases")
        if row.get("dangerous_pass_rate") is None or row["dangerous_pass_rate"] > 0.10:
            reasons.append(f"{lang}: dangerous PASS rate must be <= 10%")
        if row.get("unsafe_block_recall") is None or row["unsafe_block_recall"] < 0.80:
            reasons.append(f"{lang}: known-unsafe BLOCK recall must be >= 80%")
        if row.get("clean_pass_rate") is None or row["clean_pass_rate"] < 0.70:
            reasons.append(f"{lang}: clean PASS rate must be >= 70%")
    return {"passed": not reasons, "reasons": reasons}


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _case_input_sha256(row: dict) -> str:
    return _canonical_sha256({
        "case_id": row.get("case_id"),
        "source_text": row.get("source_text"),
        "source_language": row.get("source_language"),
        "source_contract": row.get("source_contract"),
        "candidate_text": row.get("candidate_text"),
        "candidate_language": row.get("candidate_language"),
        "expected_decision": row.get("expected_decision"),
        "fault_class": row.get("fault_class"),
    })


def provider_audit_metadata(
    row: dict, *, run_id: str, manifest_sha256: str, execution_binding: dict
) -> dict[str, str]:
    """Metadata persisted with the provider response for independent retrieval checks."""
    return {
        "signallock_run_id": run_id,
        "signallock_case_id": str(row.get("case_id", "")),
        "signallock_case_sha256": _case_input_sha256(row),
        "signallock_holdout_sha256": manifest_sha256,
        "signallock_runtime_fingerprint": str(execution_binding.get("runtime_fingerprint_sha256", "")),
    }


def _load_checkpoint(
    path: Path | None,
    *,
    manifest_sha256: str,
    provider: str,
    execution_binding: dict,
    rows_by_id: dict[str, dict],
    allow_recovery: bool,
) -> tuple[dict[str, V7CaseResult], str | None, str | None]:
    if path is None or not path.exists():
        return {}, None, None
    if not allow_recovery:
        raise ValueError(
            "pre-existing V7 checkpoint detected; certification runs must start fresh. "
            "Archive/delete it, or use explicit resume mode for a non-qualifying diagnostic run"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format_version") != "4.0":
        raise ValueError("V7 checkpoint format is not fresh-origin evidence version 4.0")
    if payload.get("manifest_sha256") != manifest_sha256 or payload.get("provider") != provider:
        raise ValueError("V7 checkpoint belongs to a different sealed holdout/provider")
    if payload.get("execution_binding") != execution_binding:
        raise ValueError("V7 checkpoint execution binding does not match the current model/runtime/config")
    run_id = str(payload.get("run_id", "")).strip()
    run_started_at_utc = str(payload.get("run_started_at_utc", "")).strip()
    if not run_id:
        raise ValueError("V7 checkpoint is missing its run_id")
    if not run_started_at_utc:
        raise ValueError("V7 checkpoint is missing run_started_at_utc")
    recovered: dict[str, V7CaseResult] = {}
    seen: set[str] = set()
    for wrapped in payload.get("cases", []):
        if not isinstance(wrapped, dict) or not isinstance(wrapped.get("result"), dict):
            raise ValueError("V7 checkpoint contains malformed case evidence")
        result = V7CaseResult(**wrapped["result"])
        if result.case_id in seen:
            raise ValueError("V7 checkpoint contains duplicate case IDs")
        seen.add(result.case_id)
        row = rows_by_id.get(result.case_id)
        if row is None:
            raise ValueError(f"V7 checkpoint contains unknown case_id {result.case_id!r}")
        if wrapped.get("case_input_sha256") != _case_input_sha256(row):
            raise ValueError(f"V7 checkpoint case input hash mismatch for {result.case_id}")
        if not result.origin_run_id or not result.executed_in_run_id:
            raise ValueError(f"V7 checkpoint case {result.case_id} is missing immutable run-origin evidence")
        recovered[result.case_id] = result
    return recovered, run_id, run_started_at_utc


def _write_checkpoint(
    path: Path | None,
    *,
    manifest_sha256: str,
    provider: str,
    execution_binding: dict,
    run_id: str,
    run_started_at_utc: str,
    rows_by_id: dict[str, dict],
    results: list[V7CaseResult],
) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format_version": "4.0",
        "run_id": run_id,
        "run_started_at_utc": run_started_at_utc,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": manifest_sha256,
        "provider": provider,
        "execution_binding": execution_binding,
        "cases": [
            {
                "case_input_sha256": _case_input_sha256(rows_by_id[r.case_id]),
                "result": asdict(r),
            }
            for r in results
        ],
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def compute_v7_metrics(
    results: list[V7CaseResult],
    *,
    quality: dict | None = None,
) -> dict:
    if not results:
        raise ValueError("V7 metrics require at least one case result")
    expected_block = [r for r in results if r.expected_decision == "BLOCK"]
    expected_pass = [r for r in results if r.expected_decision == "PASS"]
    expected_review = [r for r in results if r.expected_decision == "REVIEW"]
    dangerous_passes = sum(r.actual_decision == "PASS" for r in expected_block)
    clean_passes = sum(r.actual_decision == "PASS" for r in expected_pass)
    clean_blocks = sum(r.actual_decision == "BLOCK" for r in expected_pass)
    review_matches = sum(r.actual_decision == "REVIEW" for r in expected_review)

    by_language: dict[str, dict] = {}
    for lang in sorted({r.candidate_language.split("-")[0].casefold() for r in results}):
        lang_rows = [r for r in results if r.candidate_language.split("-")[0].casefold() == lang]
        lang_blocks = [r for r in lang_rows if r.expected_decision == "BLOCK"]
        lang_passes = [r for r in lang_rows if r.expected_decision == "PASS"]
        by_language[lang] = {
            "total": len(lang_rows),
            "expected_pass_total": len(lang_passes),
            "expected_block_total": len(lang_blocks),
            "exact_decision_accuracy": sum(r.exact_match for r in lang_rows) / len(lang_rows),
            "dangerous_pass_rate": (sum(r.actual_decision == "PASS" for r in lang_blocks) / len(lang_blocks)) if lang_blocks else None,
            "unsafe_block_recall": (sum(r.actual_decision == "BLOCK" for r in lang_blocks) / len(lang_blocks)) if lang_blocks else None,
            "clean_pass_rate": (sum(r.actual_decision == "PASS" for r in lang_passes) / len(lang_passes)) if lang_passes else None,
            "decision_counts": dict(Counter(r.actual_decision for r in lang_rows)),
        }

    dangerous_by_fault: dict[str, dict] = {}
    for fault_class in sorted({r.fault_class for r in expected_block}):
        fault_rows = [r for r in expected_block if r.fault_class == fault_class]
        passes = sum(r.actual_decision == "PASS" for r in fault_rows)
        dangerous_by_fault[fault_class] = {
            "total": len(fault_rows),
            "passes": passes,
            "pass_rate": passes / len(fault_rows),
        }

    recovered_case_count = sum(r.recovered_from_checkpoint for r in results)
    return {
        "total": len(results),
        "exact_decision_accuracy": sum(r.exact_match for r in results) / len(results),
        "dangerous_pass_rate": dangerous_passes / len(expected_block) if expected_block else None,
        "unsafe_block_recall": (sum(r.actual_decision == "BLOCK" for r in expected_block) / len(expected_block)) if expected_block else None,
        "clean_pass_rate": clean_passes / len(expected_pass) if expected_pass else None,
        "clean_block_rate": clean_blocks / len(expected_pass) if expected_pass else None,
        "expected_review_match_rate": review_matches / len(expected_review) if expected_review else None,
        "decision_counts": dict(Counter(r.actual_decision for r in results)),
        "expected_counts": dict(Counter(r.expected_decision for r in results)),
        "provider_error_cases": sum(r.provider_error is not None for r in results),
        "missing_provider_receipt_cases": sum(
            r.provider_error is None
            and (not isinstance(r.provider_receipt, dict) or not str(r.provider_receipt.get("response_id", "")).strip())
            for r in results
        ),
        "missing_stored_provider_receipt_cases": sum(
            r.provider_error is None
            and (not isinstance(r.provider_receipt, dict) or r.provider_receipt.get("stored") is not True)
            for r in results
        ),
        "checkpoint_recovered_cases": recovered_case_count,
        "live_executed_cases": len(results) - recovered_case_count,
        "dangerous_pass_by_fault_class": dangerous_by_fault,
        "quality": dict(quality or {}),
        "by_language": by_language,
    }


async def evaluate_sealed_holdout(
    holdout_path: Path,
    manifest_path: Path,
    *,
    provider: str = "openai",
    checkpoint_path: Path | None = None,
    max_attempts: int = 3,
    retry_delay_seconds: float = 0.25,
    execution_binding: dict | None = None,
    allow_checkpoint_recovery: bool = False,
) -> dict:
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    manifest = verify_seal(holdout_path, manifest_path)
    rows = load_jsonl(holdout_path)
    rows_by_id = {str(row["case_id"]): row for row in rows}
    if len(rows_by_id) != len(rows):
        raise ValueError("sealed V7 holdout contains duplicate case IDs")
    extractor = ExtractionService(provider)
    verifier = VerificationEngine()
    binding = dict(execution_binding or {})

    recovered, recovered_run_id, recovered_run_started_at = _load_checkpoint(
        checkpoint_path, manifest_sha256=manifest["sha256"], provider=provider,
        execution_binding=binding, rows_by_id=rows_by_id, allow_recovery=allow_checkpoint_recovery,
    )
    run_id = f"v7-{secrets.token_urlsafe(12)}"
    run_started_at_utc = datetime.now(timezone.utc).isoformat()
    results: list[V7CaseResult] = []
    recovered_case_count = 0

    for row in rows:
        if row["case_id"] in recovered:
            recovered_result = recovered[row["case_id"]]
            recovered_result.recovered_from_checkpoint = True
            results.append(recovered_result)
            recovered_case_count += 1
            continue
        source_contract = SafetyContract.model_validate(row["source_contract"])
        last_error: Exception | None = None
        result: V7CaseResult | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                if hasattr(extractor, "extract_with_evidence"):
                    audit_metadata = provider_audit_metadata(
                        row, run_id=run_id, manifest_sha256=manifest["sha256"], execution_binding=binding
                    )
                    candidate_contract, provider_receipt = await extractor.extract_with_evidence(
                        row["candidate_text"],
                        language=row["candidate_language"],
                        source_id=f"v7-candidate:{row['case_id']}",
                        audit_metadata=audit_metadata,
                        store=True,
                    )
                else:  # compatibility for deterministic test doubles; never qualifies without a receipt
                    candidate_contract = await extractor.extract(
                        row["candidate_text"],
                        language=row["candidate_language"],
                        source_id=f"v7-candidate:{row['case_id']}",
                    )
                    provider_receipt = None
                verdict = verifier.verify(source_contract, candidate_contract)
                candidate_payload = candidate_contract.model_dump(mode="json")
                result = V7CaseResult(
                    case_id=row["case_id"],
                    source_language=row["source_language"],
                    candidate_language=row["candidate_language"],
                    fault_class=str(row.get("fault_class", "unclassified")).casefold(),
                    expected_decision=row["expected_decision"],
                    actual_decision=verdict.decision.value,
                    exact_match=verdict.decision.value == row["expected_decision"],
                    critical_failures=list(verdict.critical_failures),
                    warnings=list(verdict.warnings),
                    candidate_contract=candidate_payload,
                    candidate_contract_sha256=_canonical_sha256(candidate_payload),
                    provider_receipt=provider_receipt,
                    attempts=attempt,
                    origin_run_id=run_id,
                    executed_in_run_id=run_id,
                )
                break
            except Exception as exc:  # provider/network/schema failure is scored as uncertainty, never omitted
                last_error = exc
                if attempt < max_attempts:
                    await asyncio.sleep(retry_delay_seconds * attempt)
        if result is None:
            message = f"provider extraction failed after {max_attempts} attempts: {last_error}"
            result = V7CaseResult(
                case_id=row["case_id"],
                source_language=row["source_language"],
                candidate_language=row["candidate_language"],
                fault_class=str(row.get("fault_class", "unclassified")).casefold(),
                expected_decision=row["expected_decision"],
                actual_decision="REVIEW",
                exact_match=row["expected_decision"] == "REVIEW",
                critical_failures=[],
                warnings=[message],
                attempts=max_attempts,
                provider_error=str(last_error),
                origin_run_id=run_id,
                executed_in_run_id=run_id,
            )
        results.append(result)
        _write_checkpoint(
            checkpoint_path, manifest_sha256=manifest["sha256"], provider=provider,
            execution_binding=binding, run_id=run_id, run_started_at_utc=run_started_at_utc,
            rows_by_id=rows_by_id, results=results
        )

    metrics = compute_v7_metrics(results, quality=manifest.get("quality") or {})
    return {
        "scope": "sealed human-reviewed multilingual holdout",
        "manifest_sha256": manifest["sha256"],
        "manifest": manifest,
        "provider": provider,
        "run_id": run_id,
        "run_started_at_utc": run_started_at_utc,
        "resumed_from_run_id": recovered_run_id,
        "resumed_from_run_started_at_utc": recovered_run_started_at,
        "execution_binding": binding,
        "metrics": metrics,
        "gate": evaluate_v7_gate(metrics),
        "cases": [asdict(r) for r in results],
    }
