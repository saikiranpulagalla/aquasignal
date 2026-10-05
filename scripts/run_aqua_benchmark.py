from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json

from aquasignal.evaluation.runner import run_cases


if __name__ == "__main__":
    result = run_cases()
    print(json.dumps(result, indent=2, sort_keys=True))
