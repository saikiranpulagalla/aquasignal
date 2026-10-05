from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from signallock.evaluation.holdout import HoldoutError
from signallock.evaluation.review_workflow import _read_jsonl, _write_jsonl, validate_authoring_packet
from signallock.providers.extraction_service import ExtractionService


async def fill(rows: list[dict], provider: str) -> list[dict]:
    service = ExtractionService(provider)
    cache: dict[tuple[str, str], dict] = {}
    out: list[dict] = []
    for row in rows:
        key = (str(row["source_language"]), str(row["source_text"]))
        if key not in cache:
            contract = await service.extract(
                row["source_text"],
                language=row["source_language"],
                source_id=f"v7-authority:{row['source_seed_id']}",
            )
            cache[key] = contract.model_dump(mode="json")
        item = dict(row)
        item["source_contract"] = cache[key]
        item["authority_extraction_provider"] = provider
        item["authority_review_required"] = True
        # Deliberately never synthesize reviewer metadata here.
        item["authority_reviewer_id"] = ""
        item["authority_reviewed_at"] = ""
        out.append(item)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Populate V7 source-contract drafts using the real structured provider; human authority review is still mandatory.")
    p.add_argument("packet", type=Path, nargs="?", default=Path("data/multilingual/v7_authoring_packet_v05.jsonl"))
    p.add_argument("--output", type=Path, default=Path("data/multilingual/v7_authoring_packet_with_authority_drafts.jsonl"))
    p.add_argument("--provider", choices=["openai"], default="openai")
    args = p.parse_args()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("V7 AUTHORITY DRAFT REFUSED: OPENAI_API_KEY is missing; no source oracle was fabricated.")
    try:
        rows = _read_jsonl(args.packet)
        validate_authoring_packet(rows, require_completed=False)
        filled = asyncio.run(fill(rows, args.provider))
    except HoldoutError as exc:
        raise SystemExit(f"V7 AUTHORITY DRAFT REFUSED: {exc}") from None
    _write_jsonl(args.output, filled)
    print(json.dumps({"rows": len(filled), "unique_source_contracts": len({r['source_text'] for r in filled}), "human_authority_review_required": True}, indent=2))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
