from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from signallock.evaluation.review_workflow import _write_jsonl, prepare_authoring_packet



def _assert_not_used_in_development(seed_path: Path) -> None:
    rows=[json.loads(x) for x in seed_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    corpus=[]
    for base in (ROOT/"tests", ROOT/"scripts", ROOT/"signallock"/"benchmark"):
        for path in base.rglob("*.py"):
            if path.resolve() == Path(__file__).resolve():
                continue
            corpus.append((path, path.read_text(encoding="utf-8", errors="ignore")))
    contaminated=[]
    for row in rows:
        text=str(row.get("text", "")).strip()
        hits=[str(p.relative_to(ROOT)) for p,c in corpus if text and text in c]
        if hits:
            contaminated.append({"case_id":row.get("case_id"),"hits":hits})
    if contaminated:
        raise SystemExit("V7 PREP REFUSED: challenge source seeds already appear in development/test code: "+json.dumps(contaminated))

def main() -> None:
    p = argparse.ArgumentParser(description="Create the 24-case V7 human authoring packet; does not generate or preapprove candidates.")
    p.add_argument("--official-seeds", type=Path, default=Path("data/multilingual/v7_source_seeds.jsonl"))
    p.add_argument("--challenge-seeds", type=Path, default=Path("data/multilingual/v7_challenge_source_seeds_v05.jsonl"))
    p.add_argument("--output", type=Path, default=Path("data/multilingual/v7_authoring_packet_v05.jsonl"))
    args = p.parse_args()
    _assert_not_used_in_development(args.challenge_seeds)
    rows = prepare_authoring_packet(args.official_seeds, args.challenge_seeds)
    _write_jsonl(args.output, rows)
    summary = {
        "rows": len(rows),
        "hi": sum(r["candidate_language"] == "hi" for r in rows),
        "te": sum(r["candidate_language"] == "te" for r in rows),
        "clean": sum(r["fault_class"] == "clean" for r in rows),
        "unsafe": sum(r["fault_class"] != "clean" for r in rows),
        "candidate_text_generated": False,
        "human_review_fabricated": False,
    }
    print(json.dumps(summary, indent=2))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
