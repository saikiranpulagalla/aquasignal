#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from signallock.benchmark.runner import run_demo_benchmark


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/results/dev_benchmark.json")
    args = parser.parse_args()
    report = run_demo_benchmark()
    report["metadata"] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_type": "controlled-development-fault-injection",
        "warning": "Do not present this development benchmark as external or held-out real-world accuracy.",
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["metrics"], indent=2))
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
