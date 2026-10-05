from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aquasignal.evaluation.evidence import verify_release_evidence


if __name__ == "__main__":
    report = verify_release_evidence()
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["verified"] else 2)
