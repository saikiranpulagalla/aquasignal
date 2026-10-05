from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from signallock.evaluation.holdout import HoldoutError
from signallock.evaluation.v7_provider_evidence import verify_v7_provider_evidence


def main() -> None:
    p = argparse.ArgumentParser(description="Live-retrieve and verify every stored OpenAI response used by V7.")
    p.add_argument("--result", type=Path, default=Path("data/results/v7_multilingual_holdout.json"))
    p.add_argument("--holdout", type=Path, default=Path("data/holdout/v7_multilingual_holdout.jsonl"))
    p.add_argument("--manifest", type=Path, default=Path("data/holdout/v7_multilingual_holdout.manifest.json"))
    p.add_argument("--output", type=Path, default=Path("data/results/v7_provider_verification.json"))
    args = p.parse_args()
    if args.output.exists():
        raise SystemExit(f"V7 PROVIDER VERIFY REFUSED: output already exists at {args.output}")
    try:
        receipt = asyncio.run(verify_v7_provider_evidence(
            args.result, args.holdout, args.manifest, root=ROOT, require_trusted_runtime=True
        ))
    except (HoldoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"V7 PROVIDER VERIFY FAILED: {exc}") from None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
