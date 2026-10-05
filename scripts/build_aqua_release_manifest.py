from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import sys
from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT = ROOT / "RELEASE_MANIFEST.json"


def selected_files() -> list[Path]:
    files: set[Path] = set()
    for directory in ("aquasignal", "signallock", "apps", "web_aqua", "tests", "scripts"):
        for path in (ROOT / directory).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                files.add(path)
    for rel in (
        "pyproject.toml", "requirements.lock", "requirements-dev.lock", "Dockerfile", ".dockerignore",
        ".env.example", "Makefile", ".github/workflows/test.yml", "data/aqua/demo_resilience_context.csv",
        "data/aqua/demo_oah_observation.json", "data/aqua/holdout_v17.jsonl",
        "data/aqua/holdout_v17.manifest.json", "data/results/aqua_holdout_v17_result.json",
    ):
        path = ROOT / rel
        if path.exists():
            files.add(path)
    return sorted(files, key=lambda p: p.relative_to(ROOT).as_posix())


def tree_hash(files: list[Path]) -> str:
    h = hashlib.sha256()
    for path in files:
        rel = path.relative_to(ROOT).as_posix().encode("utf-8")
        h.update(rel + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_output(*args: str) -> str | None:
    """Return Git metadata only when this source tree is a real checkout."""
    try:
        proc = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def source_provenance() -> tuple[str | None, str | None]:
    if _git_output("rev-parse", "--is-inside-work-tree") != "true":
        return None, None
    return _git_output("rev-parse", "HEAD"), _git_output("describe", "--exact-match", "--tags", "HEAD")


def artifact_sha256(path_value: str | None, *, label: str) -> tuple[str | None, str | None]:
    if path_value is None:
        return None, None
    path = Path(path_value).resolve()
    if not path.is_file():
        raise SystemExit(f"release manifest refused: {label} does not exist or is not a file: {path}")
    return path.name, sha256(path)


def collected_count(*paths: str) -> int:
    cmd = [sys.executable, "-m", "pytest", "--collect-only", "--override-ini=addopts=", "-q", *paths]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True)
    match = re.search(r"(\d+) tests collected", proc.stdout)
    if not match:
        raise RuntimeError(f"could not determine pytest collection count from: {proc.stdout[-500:]}")
    return int(match.group(1))


def main(argv: list[str] | None = None) -> None:
    parser = ArgumentParser(description="Build an AquaSignal release provenance manifest.")
    parser.add_argument("--source-archive", help="path to the final source archive to hash")
    parser.add_argument("--wheel", help="path to the final wheel to hash")
    args = parser.parse_args(argv)

    from aquasignal import __version__
    from aquasignal.evaluation.evidence import MANIFEST, RESULT, verify_release_evidence
    from aquasignal.evaluation.runner import run_cases

    holdout = verify_release_evidence()
    if not holdout["verified"] or not holdout["qualified"]:
        raise SystemExit("release manifest refused: frozen holdout evidence is stale or unqualified")
    dev = run_cases()
    files = selected_files()
    source_commit, release_tag = source_provenance()
    source_archive_name, source_archive_hash = artifact_sha256(args.source_archive, label="source archive")
    wheel_name, wheel_hash = artifact_sha256(args.wheel, label="wheel")
    manifest = {
        "kind": "AquaSignal OneAquaHealth release evidence identity",
        "release_id": f"aquasignal-oneaquahealth-v{__version__}",
        "version": __version__,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "source_commit": source_commit,
        "release_tag": release_tag,
        "source_archive_filename": source_archive_name,
        "source_archive_sha256": source_archive_hash,
        "wheel_filename": wheel_name,
        "wheel_sha256": wheel_hash,
        "release_evidence_tree_sha256": tree_hash(files),
        "release_evidence_file_count": len(files),
        "semantic_profile": "freshwater-protective-communication-v1",
        "semantic_fingerprint": holdout["semantic_fingerprint"],
        "evaluator_fingerprint": holdout["evaluator_fingerprint"],
        "requirements_lock_sha256": holdout["requirements_lock_sha256"],
        "holdout": {
            "id": holdout["holdout"],
            "dataset_sha256": holdout["dataset_sha256"],
            "manifest_sha256": sha256(MANIFEST),
            "result_sha256": sha256(RESULT),
            "qualified": holdout["qualified"],
            "metrics": holdout["metrics"],
        },
        "dev_benchmark": {
            k: dev[k]
            for k in (
                "total", "unsafe_total", "unsafe_pass", "unsafe_block", "unsafe_review",
                "unsafe_source_review", "clean_total", "clean_pass", "clean_review", "clean_block",
                "clean_source_review",
            )
        },
        "tests": {
            "inherited_signallock": collected_count("tests/unit", "tests/integration", "tests/regression"),
            "aqua_specific": collected_count("tests/aqua"),
            "combined": collected_count(),
        },
        "disclosures": [
            "Aqua holdout V17 is author-curated and is not independent external validation.",
            "Earlier holdout iterations are retained/burned when a defect or post-seal change invalidated them; V17 is the current verified evidence.",
            "Inherited SignalLock tests are not relabeled as freshwater validation.",
            "AquaSignal is a prototype human-review aid, not a safety certification or environmental/public-health authority.",
            "Resilience-compatible CSV/FHIR context proves server-bound import provenance, not independent authenticity of the upstream dataset.",
            "Integrity receipts use HMAC-SHA256 and are server-verifiable, not public-key attestations.",
        ],
    }
    OUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
