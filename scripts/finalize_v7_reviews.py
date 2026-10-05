from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from signallock.evaluation.holdout import HoldoutError, validate_v7_quality
from signallock.evaluation.review_workflow import _write_jsonl, finalize_reviewed_holdout


def main() -> None:
    p = argparse.ArgumentParser(description="Merge independent V7 authoring/authority/primary/secondary review evidence into strict-sealer input.")
    p.add_argument("authored_packet", type=Path)
    p.add_argument("primary_reviews", type=Path)
    p.add_argument("secondary_reviews", type=Path)
    p.add_argument("--mapping", type=Path, default=Path("data/multilingual/v7_blind_review_map.json"), help="Private mapping produced with the blinded review sheets")
    p.add_argument("--output", type=Path, default=Path("data/multilingual/v7_reviewed.jsonl"))
    args = p.parse_args()
    try:
        rows = finalize_reviewed_holdout(args.authored_packet, args.primary_reviews, args.secondary_reviews, args.mapping)
        quality = validate_v7_quality(rows)
    except HoldoutError as exc:
        raise SystemExit(f"V7 FINALIZATION REFUSED: {exc}") from None
    _write_jsonl(args.output, rows)
    print(json.dumps({"output": str(args.output), "quality": quality}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
