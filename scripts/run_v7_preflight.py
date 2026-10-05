from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from signallock.evaluation.holdout import HoldoutError, verify_code_binding, verify_seal, verify_v7_runtime_binding
from signallock.evaluation.release import resolve_release_identity
from signallock.evaluation.environment import execution_environment, environment_sha256, qualification_environment_errors
from signallock.evaluation.review_workflow import _read_jsonl, validate_authoring_packet


def main() -> None:
    holdout = ROOT / "data/holdout/v7_multilingual_holdout.jsonl"
    manifest = ROOT / "data/holdout/v7_multilingual_holdout.manifest.json"
    audit = ROOT / "data/results/postrepair_audit.json"
    output = ROOT / "data/results/v7_preflight.json"
    provider = "openai"
    model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

    audit_passed = False
    if audit.exists():
        try:
            audit_passed = json.loads(audit.read_text(encoding="utf-8")).get("passed") is True
        except Exception:
            audit_passed = False

    identity = resolve_release_identity(ROOT)
    environment = execution_environment(ROOT)
    environment_errors = qualification_environment_errors(ROOT, environment)

    authoring_packet = ROOT / "data/multilingual/v7_authoring_packet_v05.jsonl"
    authoring_packet_state = "missing"
    authoring_packet_error = None
    if authoring_packet.exists():
        try:
            authoring_rows = _read_jsonl(authoring_packet)
            validate_authoring_packet(authoring_rows, require_completed=False)
            completed = all(
                str(r.get("candidate_text", "")).strip()
                and str(r.get("author_id", "")).strip()
                and isinstance(r.get("source_contract"), dict)
                and str(r.get("authority_reviewer_id", "")).strip()
                and str(r.get("authority_reviewed_at", "")).strip()
                for r in authoring_rows
            )
            if completed:
                validate_authoring_packet(authoring_rows, require_completed=True)
                authoring_packet_state = "authored-authority-reviewed"
            else:
                authoring_packet_state = "planned-valid-awaiting-human-work"
        except (HoldoutError, ValueError) as exc:
            authoring_packet_state = "invalid"
            authoring_packet_error = str(exc)

    holdout_state = "missing"
    holdout_error = None
    if holdout.exists() and manifest.exists():
        try:
            sealed_manifest = verify_seal(holdout, manifest)
            if not identity["identity"] or not identity["clean"]:
                raise HoldoutError(identity["error"] or "runtime has no clean identity")
            verify_code_binding(sealed_manifest, identity["identity"])
            verify_v7_runtime_binding(sealed_manifest, provider=provider, model=model)
            holdout_state = "sealed-valid-bound-strict"
        except (HoldoutError, ValueError) as exc:
            holdout_state = "invalid"
            holdout_error = str(exc)

    checks = {
        "qualification_environment_compliant": not environment_errors,
        "environment_errors": environment_errors,
        "environment_sha256": environment_sha256(environment),
        "postrepair_forensic_audit_passed": audit_passed,
        "openai_api_key_present": bool(os.getenv("OPENAI_API_KEY")),
        "adaption_api_key_present": bool(os.getenv("ADAPTION_API_KEY")),
        "sealed_multilingual_holdout": holdout_state,
        "runtime_identity_source": identity["source"],
        "runtime_identity": identity["identity"],
        "runtime_tree_sha256": identity["runtime_tree_sha256"],
        "runtime_code_clean": identity["clean"],
        "v7_runner_present": (ROOT / "scripts/run_v7_multilingual.py").exists(),
        "holdout_sealer_present": (ROOT / "scripts/seal_v7_holdout.py").exists(),
        "review_draft_generator_present": (ROOT / "scripts/generate_v7_review_draft.py").exists(),
        "qualification_kit_present": (ROOT / "scripts/prepare_v7_qualification_kit.py").exists(),
        "blind_review_builder_present": (ROOT / "scripts/prepare_v7_blind_reviews.py").exists(),
        "review_finalizer_present": (ROOT / "scripts/finalize_v7_reviews.py").exists(),
        "authoring_packet": authoring_packet_state,
        "sealed_model": model,
        "default_checkpoint_present": (ROOT / "data/results/v7_multilingual_checkpoint.json").exists(),
        "default_result_present": (ROOT / "data/results/v7_multilingual_holdout.json").exists(),
        "default_evidence_receipt_present": (ROOT / "data/results/v7_evidence_verification.json").exists(),
        "default_provider_verification_present": (ROOT / "data/results/v7_provider_verification.json").exists(),
    }
    ready_to_execute_v7 = (
        checks["qualification_environment_compliant"]
        and         checks["postrepair_forensic_audit_passed"]
        and checks["openai_api_key_present"]
        and checks["sealed_multilingual_holdout"] == "sealed-valid-bound-strict"
        and checks["runtime_code_clean"]
        and checks["v7_runner_present"]
        and not checks["default_checkpoint_present"]
        and not checks["default_result_present"]
        and not checks["default_evidence_receipt_present"]
        and not checks["default_provider_verification_present"]
    )
    report = {
        "scope": "V7 multilingual holdout preflight; not a model-quality result",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "holdout_error": holdout_error,
        "authoring_packet_error": authoring_packet_error,
        "ready_to_execute_v7": ready_to_execute_v7,
        "next_required_actions": [] if ready_to_execute_v7 else [
            action for needed, action in [
                (bool(environment_errors), "Install a qualification environment satisfying declared dependencies: " + "; ".join(environment_errors)),
                (not checks["openai_api_key_present"], "Configure OPENAI_API_KEY for real multilingual structured extraction."),
                (checks["authoring_packet"] == "missing", "Run scripts/prepare_v7_qualification_kit.py to create the frozen 24-case human authoring plan."),
                (checks["authoring_packet"] == "invalid", "Repair the invalid V7 authoring packet before any review work."),
                (checks["authoring_packet"] == "planned-valid-awaiting-human-work", "Complete authority review + human candidate authoring, then produce blind reviews and finalize v7_reviewed.jsonl."),
                (checks["sealed_multilingual_holdout"] != "sealed-valid-bound-strict", "Finalize and seal the independently reviewed Hindi/Telugu V7 holdout with the strict V7 sealer."),
                (not checks["runtime_code_clean"], "Use a clean Git checkout, or set SIGNALLOCK_TRUSTED_RUNTIME_SHA256 to the externally published runtime digest for the packaged release."),
                (not checks["postrepair_forensic_audit_passed"], "Re-run scripts/run_postrepair_audit.py and fix any regression before V7."),
                (checks["default_checkpoint_present"], "Archive/remove the existing V7 checkpoint before a fresh certification run; --resume is diagnostic-only and cannot qualify."),
                (checks["default_result_present"], "Archive the existing V7 result and choose a fresh output path; qualification evidence must not be overwritten."),
                (checks["default_evidence_receipt_present"], "Archive the existing V7 evidence receipt before a fresh qualification run; evidence must not be overwritten."),
                (checks["default_provider_verification_present"], "Archive the existing V7 provider retrieval receipt before a fresh qualification run; evidence must not be overwritten."),
            ] if needed
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not ready_to_execute_v7:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
