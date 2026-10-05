from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aquasignal.evaluation.cases import AquaCase

DATA = ROOT / "data" / "aqua" / "holdout_v6.jsonl"
MANIFEST = ROOT / "data" / "aqua" / "holdout_v6.manifest.json"
SEMANTIC_FILES = [
    "aquasignal/domain/freshwater.py",
    "aquasignal/integrity/verifier.py",
    "signallock/contracts/schema.py",
    "signallock/contracts/normalization.py",
    "signallock/verification/engine.py",
    "aquasignal/evaluation/cases.py",
    "aquasignal/evaluation/runner.py",
    "aquasignal/evaluation/evidence.py",
    "scripts/run_aqua_holdout_v6.py",
]
CRITICAL_BLOCK_FAMILIES = [
    "time_reversal", "location_reversal", "site_identifier_change", "audience_omission",
    "action_omission", "prohibition_loss", "unauthorized_addition", "constraint_weakening",
    "quantity_change", "exclusivity_loss",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(files: list[str]) -> str:
    h = hashlib.sha256()
    for rel in files:
        h.update(rel.encode() + b"\0" + (ROOT / rel).read_bytes() + b"\0")
    return h.hexdigest()


if __name__ == "__main__":
    if not DATA.exists():
        raise SystemExit("holdout_v6.jsonl does not exist")
    rows = [json.loads(x) for x in DATA.read_text(encoding="utf-8").splitlines() if x.strip()]
    cases = [AquaCase(**x) for x in rows]
    if len({x.case_id for x in cases}) != len(cases):
        raise SystemExit("duplicate case_id in V6")
    manifest = {
        "schema_version": 2,
        "holdout": "aqua-holdout-v6",
        "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
        "case_count": len(cases),
        "unsafe_count": sum(not x.safe_equivalent for x in cases),
        "clean_count": sum(x.safe_equivalent for x in cases),
        "dataset_sha256": sha256(DATA),
        "semantic_files": SEMANTIC_FILES,
        "semantic_fingerprint": fingerprint(SEMANTIC_FILES),
        "critical_block_families": CRITICAL_BLOCK_FAMILIES,
        "min_clean_pass_rate": 0.80,
        "max_clean_block_rate": 0.05,
        "note": "Author-curated frozen V6 release holdout. Not an independent external evaluation. Sealed after red-team hardening; any sealed semantic dependency change burns the result.",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
