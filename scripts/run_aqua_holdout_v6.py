from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aquasignal.evaluation.cases import AquaCase
from aquasignal.evaluation.evidence import sha256, semantic_fingerprint
from aquasignal.evaluation.runner import run_cases

DATA = ROOT / "data" / "aqua" / "holdout_v6.jsonl"
MANIFEST = ROOT / "data" / "aqua" / "holdout_v6.manifest.json"
RESULT = ROOT / "data" / "results" / "aqua_holdout_v6_result.json"


def qualify(metrics: dict, manifest: dict) -> bool:
    if metrics["unsafe_pass"] != 0 or metrics["clean_pass_rate"] < manifest["min_clean_pass_rate"] or metrics["clean_block_rate"] > manifest["max_clean_block_rate"]:
        return False
    if metrics["expected_failures"]:
        return False
    for family in manifest["critical_block_families"]:
        counts = metrics["per_family"].get(family, {})
        if counts and counts.get("BLOCK", 0) != sum(counts.values()):
            return False
    return True


if __name__ == "__main__":
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if sha256(DATA) != manifest["dataset_sha256"]:
        raise SystemExit("holdout dataset hash mismatch")
    if semantic_fingerprint(manifest["semantic_files"]) != manifest["semantic_fingerprint"]:
        raise SystemExit("semantic dependency closure changed after V6 sealing")
    rows = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines() if line.strip()]
    metrics = run_cases([AquaCase(**row) for row in rows])
    qualified = qualify(metrics, manifest)
    result = {
        "holdout": manifest["holdout"],
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": manifest["dataset_sha256"],
        "semantic_fingerprint": manifest["semantic_fingerprint"],
        "qualified_against_declared_release_gates": qualified,
        "metrics": metrics,
        "disclosure": manifest["note"],
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if qualified else 2)
