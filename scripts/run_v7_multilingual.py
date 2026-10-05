from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from signallock.evaluation.v7 import evaluate_sealed_holdout
from signallock.evaluation.holdout import HoldoutError, verify_code_binding, verify_seal, verify_v7_runtime_binding
from signallock.evaluation.release import resolve_release_identity
from signallock.evaluation.v7_evidence import verify_v7_evidence
from signallock.evaluation.v7_provider_evidence import verify_v7_provider_evidence


def main() -> None:
    p = argparse.ArgumentParser(description="Run SignalLock V7 on a strictly sealed multilingual holdout.")
    p.add_argument("--holdout", type=Path, default=Path("data/holdout/v7_multilingual_holdout.jsonl"))
    p.add_argument("--manifest", type=Path, default=Path("data/holdout/v7_multilingual_holdout.manifest.json"))
    p.add_argument("--provider", choices=["openai"], default="openai")
    p.add_argument("--output", type=Path, default=Path("data/results/v7_multilingual_holdout.json"))
    p.add_argument("--checkpoint", type=Path, default=Path("data/results/v7_multilingual_checkpoint.json"))
    p.add_argument("--evidence-output", type=Path, default=Path("data/results/v7_evidence_verification.json"))
    p.add_argument("--provider-evidence-output", type=Path, default=Path("data/results/v7_provider_verification.json"))
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument("--resume", action="store_true", help="Resume a checkpoint for diagnostics; resumed runs can never qualify V7")
    args = p.parse_args()

    if args.provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("V7 REFUSED: OPENAI_API_KEY is missing; real multilingual extraction was not executed.")
    model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

    try:
        identity = resolve_release_identity(ROOT)
        if not identity["clean"] or not identity["identity"]:
            raise HoldoutError(identity["error"] or "runtime has no clean immutable identity")
        manifest = verify_seal(args.holdout, args.manifest)
        verify_code_binding(manifest, identity["identity"])
        verify_v7_runtime_binding(manifest, provider=args.provider, model=model)
    except (HoldoutError, ValueError, OSError) as exc:
        raise SystemExit(f"V7 REFUSED: {exc}") from None

    execution_binding = {
        "provider": args.provider,
        "model": model,
        "runtime_identity": identity["identity"],
        "runtime_tree_sha256": identity["runtime_tree_sha256"],
        "runtime_fingerprint_sha256": manifest["runtime_binding"]["fingerprint_sha256"],
        "environment_sha256": manifest["runtime_binding"]["environment_sha256"],
        "max_attempts": args.max_attempts,
    }
    if args.output.exists():
        raise SystemExit(
            f"V7 REFUSED: output already exists at {args.output}; preserve prior evidence and choose a fresh --output path"
        )
    if args.evidence_output.exists():
        raise SystemExit(
            f"V7 REFUSED: evidence receipt already exists at {args.evidence_output}; preserve prior evidence and choose a fresh --evidence-output path"
        )
    if args.provider_evidence_output.exists():
        raise SystemExit(
            f"V7 REFUSED: provider verification receipt already exists at {args.provider_evidence_output}; preserve prior evidence and choose a fresh --provider-evidence-output path"
        )
    report = asyncio.run(evaluate_sealed_holdout(
        args.holdout,
        args.manifest,
        provider=args.provider,
        checkpoint_path=args.checkpoint,
        max_attempts=args.max_attempts,
        execution_binding=execution_binding,
        allow_checkpoint_recovery=args.resume,
    ))
    report["executed_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["runtime_identity"] = identity
    report["model"] = model
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        evidence_receipt = verify_v7_evidence(
            args.output, args.holdout, args.manifest, root=ROOT, require_trusted_runtime=True
        )
    except (HoldoutError, ValueError, OSError) as exc:
        raise SystemExit(f"V7 EVIDENCE REPLAY FAILED AFTER RUN: {exc}") from None
    args.evidence_output.parent.mkdir(parents=True, exist_ok=True)
    args.evidence_output.write_text(
        json.dumps(evidence_receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    try:
        provider_evidence = asyncio.run(verify_v7_provider_evidence(
            args.output, args.holdout, args.manifest, root=ROOT, require_trusted_runtime=True
        ))
    except (HoldoutError, ValueError, OSError) as exc:
        raise SystemExit(f"V7 PROVIDER RETRIEVAL VERIFY FAILED AFTER RUN: {exc}") from None
    args.provider_evidence_output.parent.mkdir(parents=True, exist_ok=True)
    args.provider_evidence_output.write_text(
        json.dumps(provider_evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    print(f"wrote {args.output}")
    print(f"verified replay evidence -> {args.evidence_output}")
    print(f"verified provider retrieval evidence -> {args.provider_evidence_output}")
    if report["gate"]["passed"] is not True:
        print(json.dumps({"gate": report["gate"]}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
