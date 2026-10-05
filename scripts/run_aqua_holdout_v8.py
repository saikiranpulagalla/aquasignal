from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aquasignal.evaluation.cases import AquaCase
from aquasignal.evaluation.evidence import _qualify, semantic_fingerprint, sha256
from aquasignal.evaluation.runner import run_cases

DATA = ROOT / "data" / "aqua" / "holdout_v8.jsonl"
MANIFEST = ROOT / "data" / "aqua" / "holdout_v8.manifest.json"
RESULT = ROOT / "data" / "results" / "aqua_holdout_v8_result.json"


if __name__ == "__main__":
    if RESULT.exists():
        raise SystemExit("V8 result already exists; frozen holdout must not be rerun as if first execution")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    checks = [
        (sha256(DATA), manifest["dataset_sha256"], "holdout dataset hash mismatch"),
        (semantic_fingerprint(manifest["semantic_files"]), manifest["semantic_fingerprint"], "semantic dependency closure changed after V8 sealing"),
        (semantic_fingerprint(manifest["evaluator_files"]), manifest["evaluator_fingerprint"], "evaluation machinery changed after V8 sealing"),
        (sha256(ROOT / "requirements.lock"), manifest["requirements_lock_sha256"], "runtime lock changed after V8 sealing"),
    ]
    for actual, expected, message in checks:
        if actual != expected:
            raise SystemExit(message)
    rows = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines() if line.strip()]
    metrics = run_cases([AquaCase(**row) for row in rows])
    qualified, qualification_errors = _qualify(metrics, manifest)
    result = {
        "holdout": manifest["holdout"],
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": manifest["dataset_sha256"],
        "semantic_fingerprint": manifest["semantic_fingerprint"],
        "evaluator_fingerprint": manifest["evaluator_fingerprint"],
        "requirements_lock_sha256": manifest["requirements_lock_sha256"],
        "qualified_against_declared_release_gates": qualified,
        "qualification_errors": qualification_errors,
        "metrics": metrics,
        "disclosure": manifest["note"],
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    raise SystemExit(0 if qualified else 2)
