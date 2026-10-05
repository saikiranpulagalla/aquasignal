from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from signallock.evaluation.holdout import HoldoutError, sha256_file
from signallock.evaluation.v7_evidence import verify_v7_evidence
from signallock.evaluation.v7_provider_evidence import verify_v7_provider_evidence


def main() -> None:
    p = argparse.ArgumentParser(description="Fail-closed V8 unlock check; requires replay-verified passing V7 evidence.")
    p.add_argument("--result", type=Path, default=Path("data/results/v7_multilingual_holdout.json"))
    p.add_argument("--holdout", type=Path, default=Path("data/holdout/v7_multilingual_holdout.jsonl"))
    p.add_argument("--manifest", type=Path, default=Path("data/holdout/v7_multilingual_holdout.manifest.json"))
    p.add_argument("--verification", type=Path, default=Path("data/results/v7_evidence_verification.json"))
    p.add_argument("--provider-verification", type=Path, default=Path("data/results/v7_provider_verification.json"))
    args = p.parse_args()
    try:
        replay = verify_v7_evidence(
            args.result, args.holdout, args.manifest, root=ROOT, require_trusted_runtime=True
        )
        if not args.verification.exists():
            raise HoldoutError("persisted V7 evidence verification receipt is missing")
        saved = json.loads(args.verification.read_text(encoding="utf-8"))
        if saved.get("verified") is not True:
            raise HoldoutError("persisted V7 evidence receipt is not verified")
        if saved.get("result_sha256") != sha256_file(args.result):
            raise HoldoutError("V7 result changed after evidence verification")
        if saved.get("sealed_holdout_sha256") != replay.get("sealed_holdout_sha256"):
            raise HoldoutError("V7 verification receipt belongs to a different holdout")
        if saved.get("manifest_file_sha256") != sha256_file(args.manifest):
            raise HoldoutError("V7 manifest changed after evidence verification")
        for field in ("run_id", "run_started_at_utc", "provider", "model"):
            if saved.get(field) != replay.get(field):
                raise HoldoutError(f"persisted V7 verification receipt {field} differs from replay")
        if saved.get("gate") != replay.get("gate"):
            raise HoldoutError("persisted V7 verification gate differs from fresh replay")
        saved_runtime = saved.get("runtime_identity") or {}
        replay_runtime = replay.get("runtime_identity") or {}
        for field in ("identity", "runtime_tree_sha256"):
            if saved_runtime.get(field) != replay_runtime.get(field):
                raise HoldoutError(f"persisted V7 verification runtime {field} differs from fresh replay")
        if replay["gate"]["passed"] is not True:
            raise HoldoutError("V7 qualification gate did not pass")
        if replay.get("resumed_from_run_id"):
            raise HoldoutError("V7 qualification was started from a prior checkpoint run")
        if replay.get("provider_error_cases") != 0 or replay.get("checkpoint_recovered_cases") != 0:
            raise HoldoutError("V7 qualification is not a fresh error-free live run")
        live_provider = asyncio.run(verify_v7_provider_evidence(
            args.result, args.holdout, args.manifest, root=ROOT, require_trusted_runtime=True
        ))
        if not args.provider_verification.exists():
            raise HoldoutError("persisted V7 provider retrieval receipt is missing")
        saved_provider = json.loads(args.provider_verification.read_text(encoding="utf-8"))
        if saved_provider.get("verified") is not True:
            raise HoldoutError("persisted V7 provider retrieval receipt is not verified")
        for field in ("result_sha256", "sealed_holdout_sha256", "manifest_file_sha256", "run_id", "provider", "model", "provider_verified_cases"):
            if saved_provider.get(field) != live_provider.get(field):
                raise HoldoutError(f"persisted V7 provider verification {field} differs from fresh provider retrieval")
        if saved_provider.get("offline_replay_gate") != live_provider.get("offline_replay_gate"):
            raise HoldoutError("persisted V7 provider verification gate differs from fresh provider retrieval")
        if saved_provider.get("cases") != live_provider.get("cases"):
            raise HoldoutError("persisted V7 provider case receipts differ from fresh provider retrieval")
    except (HoldoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"V8 LOCKED: {exc}") from None
    print(json.dumps({
        "v8_unlocked": True,
        "result_sha256": replay["result_sha256"],
        "run_id": replay["run_id"],
        "gate": replay["gate"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
