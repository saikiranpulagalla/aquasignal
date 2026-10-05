from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from signallock.evaluation.holdout import HoldoutError, seal_v7_holdout_strict
from signallock.evaluation.release import resolve_release_identity


def main() -> None:
    p = argparse.ArgumentParser(description="Strictly seal a human-reviewed multilingual V7 holdout.")
    p.add_argument("input", type=Path, help="Human-reviewed JSONL input")
    p.add_argument("--output", type=Path, default=Path("data/holdout/v7_multilingual_holdout.jsonl"))
    p.add_argument("--manifest", type=Path, default=Path("data/holdout/v7_multilingual_holdout.manifest.json"))
    p.add_argument("--schema-version", default="1.0")
    p.add_argument("--verifier-version", default="0.12.0-fifth-order-hardening")
    p.add_argument("--extractor-version", default="openai-structured-v2-relational")
    p.add_argument("--prompt-version", default="multilingual-contract-v2-relational")
    p.add_argument("--provider", choices=["openai"], default="openai")
    p.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"))
    args = p.parse_args()
    try:
        identity = resolve_release_identity(ROOT)
        if not identity["clean"] or not identity["identity"]:
            raise HoldoutError(f"runtime code has no clean immutable identity: {identity['error']}")
        manifest = seal_v7_holdout_strict(
            args.input,
            args.output,
            args.manifest,
            schema_version=args.schema_version,
            verifier_version=args.verifier_version,
            extractor_version=args.extractor_version,
            prompt_version=args.prompt_version,
            code_commit=identity["identity"],
            provider=args.provider,
            model=args.model,
            provider_config={"store": True},
        )
    except (HoldoutError, OSError, ValueError) as exc:
        raise SystemExit(f"V7 SEAL REFUSED: {exc}") from None
    print(f"sealed {manifest['rows']} rows: {manifest['sha256']}")
    print(f"runtime fingerprint: {manifest['runtime_binding']['fingerprint_sha256']}")


if __name__ == "__main__":
    main()
