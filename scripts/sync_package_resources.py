from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "aquasignal" / "resources"

# Remove prior frozen-evidence copies so an installed wheel cannot accidentally
# serve stale evidence from an older release candidate.
for pattern in ("data/aqua/holdout_v*.jsonl", "data/aqua/holdout_v*.manifest.json", "data/results/aqua_holdout_v*_result.json"):
    for stale in DEST.glob(pattern):
        stale.unlink()

for rel in (
    "web_aqua/index.html",
    "web_aqua/app.js",
    "web_aqua/app.css",
    "data/aqua/demo_resilience_context.csv",
    "data/aqua/demo_oah_observation.json",
    "data/aqua/holdout_v17.jsonl",
    "data/aqua/holdout_v17.manifest.json",
    "data/results/aqua_holdout_v17_result.json",
):
    src = ROOT / rel
    if not src.exists():
        raise SystemExit(f"required package resource is missing: {rel}")
    dst = DEST / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

lock_src = ROOT / "requirements.lock"
lock_dst = DEST / "requirements.lock"
shutil.copy2(lock_src, lock_dst)
print("package resources synchronized for Aqua holdout V17")
