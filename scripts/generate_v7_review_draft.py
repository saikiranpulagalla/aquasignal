from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from signallock.evaluation.draft import generate_review_draft, load_source_seeds, write_jsonl


def main() -> None:
    p = argparse.ArgumentParser(description="Generate multilingual V7 candidates for independent human review.")
    p.add_argument("source_seeds", type=Path)
    p.add_argument("--languages", nargs="+", default=["hi", "te"])
    p.add_argument("--provider", choices=["openai"], default="openai")
    p.add_argument("--output", type=Path, default=Path("data/multilingual/v7_review_draft.jsonl"))
    args = p.parse_args()
    if args.provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("V7 DRAFT REFUSED: OPENAI_API_KEY is missing; no fake translations were generated.")
    seeds = load_source_seeds(args.source_seeds)
    rows = asyncio.run(generate_review_draft(seeds, languages=args.languages, provider=args.provider))
    write_jsonl(args.output, rows)
    print(f"wrote {len(rows)} unreviewed rows to {args.output}")
    print("IMPORTANT: independently review every row, set expected_decision to PASS/REVIEW/BLOCK, and human_reviewed=true before sealing.")


if __name__ == "__main__":
    main()
