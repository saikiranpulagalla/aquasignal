from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from signallock.evaluation.review_workflow import _read_jsonl, _write_jsonl, make_blind_review_templates
from signallock.evaluation.holdout import HoldoutError


def main() -> None:
    p = argparse.ArgumentParser(description="Create blinded primary/secondary V7 review templates from a completed authoring packet.")
    p.add_argument("authored_packet", type=Path)
    p.add_argument("--primary", type=Path, default=Path("data/multilingual/v7_primary_review.jsonl"))
    p.add_argument("--secondary", type=Path, default=Path("data/multilingual/v7_secondary_review.jsonl"))
    p.add_argument("--mapping", type=Path, default=Path("data/multilingual/v7_blind_review_map.json"), help="Private mapping; never give this file to reviewers")
    args = p.parse_args()
    try:
        rows = _read_jsonl(args.authored_packet)
        primary, secondary, mapping = make_blind_review_templates(rows)
    except HoldoutError as exc:
        raise SystemExit(f"V7 REVIEW TEMPLATE REFUSED: {exc}") from None
    _write_jsonl(args.primary, primary); _write_jsonl(args.secondary, secondary)
    args.mapping.parent.mkdir(parents=True, exist_ok=True)
    args.mapping.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"primary_rows": len(primary), "secondary_rows": len(secondary), "targets_blinded": True, "opaque_review_ids": True, "orders_independently_shuffled": True, "mapping": str(args.mapping), "mapping_keep_private": True}, indent=2))


if __name__ == "__main__":
    main()
