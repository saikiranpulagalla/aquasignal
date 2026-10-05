from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path

from aquasignal.evaluation.cases import AquaCase
from aquasignal.evaluation.runner import run_cases

CODE_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DATA_ROOT = CODE_ROOT / "data"
PACKAGE_DATA_ROOT = Path(__file__).resolve().parents[1] / "resources" / "data"


def _is_source_tree(root: Path) -> bool:
    return (root / "pyproject.toml").is_file() and (root / "data" / "aqua").is_dir()


DATA_ROOT = SOURCE_DATA_ROOT if _is_source_tree(CODE_ROOT) else PACKAGE_DATA_ROOT
SOURCE_LOCK = CODE_ROOT / "requirements.lock"
PACKAGE_LOCK = Path(__file__).resolve().parents[1] / "resources" / "requirements.lock"
RUNTIME_LOCK = SOURCE_LOCK if _is_source_tree(CODE_ROOT) and SOURCE_LOCK.is_file() else PACKAGE_LOCK

DATA = DATA_ROOT / "aqua" / "holdout_v17.jsonl"
MANIFEST = DATA_ROOT / "aqua" / "holdout_v17.manifest.json"
RESULT = DATA_ROOT / "results" / "aqua_holdout_v17_result.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def semantic_fingerprint(files: list[str]) -> str:
    h = hashlib.sha256()
    for rel in files:
        path = CODE_ROOT / rel
        if not path.exists():
            raise FileNotFoundError(f"sealed semantic dependency is missing: {rel}")
        h.update(rel.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()


def _load_cases() -> list[AquaCase]:
    rows = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [AquaCase(**row) for row in rows]


def _metric_view(metrics: dict) -> dict:
    keys = (
        "total", "unsafe_total", "unsafe_pass", "unsafe_block", "unsafe_review", "unsafe_source_review",
        "clean_total", "clean_pass", "clean_review", "clean_block", "clean_source_review",
        "unsafe_pass_rate", "unsafe_block_rate", "clean_pass_rate", "clean_block_rate",
        "expected_failures", "expected_pass_rate", "per_family", "cases",
    )
    return {k: metrics.get(k) for k in keys}


def _validate_metric_arithmetic(metrics: dict) -> list[str]:
    errors: list[str] = []
    unsafe_sum = sum(int(metrics.get(k) or 0) for k in ("unsafe_pass", "unsafe_block", "unsafe_review", "unsafe_source_review"))
    clean_sum = sum(int(metrics.get(k) or 0) for k in ("clean_pass", "clean_block", "clean_review", "clean_source_review"))
    if unsafe_sum != int(metrics.get("unsafe_total") or -1):
        errors.append("unsafe metric counts do not sum to unsafe_total")
    if clean_sum != int(metrics.get("clean_total") or -1):
        errors.append("clean metric counts do not sum to clean_total")
    if unsafe_sum + clean_sum != int(metrics.get("total") or -1):
        errors.append("clean+unsafe totals do not sum to total")
    return errors


def _validate_manifest_counts(metrics: dict, manifest: dict) -> list[str]:
    errors: list[str] = []
    expected = {
        "case_count": int(metrics.get("total") or 0),
        "unsafe_count": int(metrics.get("unsafe_total") or 0),
        "clean_count": int(metrics.get("clean_total") or 0),
    }
    for key, actual in expected.items():
        if int(manifest.get(key, -1)) != actual:
            errors.append(f"manifest {key} does not match recomputed metrics")
    return errors


def _qualify(metrics: dict, manifest: dict) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if metrics.get("unsafe_pass") != 0:
        errors.append("holdout unsafe_pass must equal 0")
    if float(metrics.get("clean_pass_rate") or 0.0) < float(manifest.get("min_clean_pass_rate", 0.80)):
        errors.append("holdout clean_pass_rate is below release threshold")
    if float(metrics.get("clean_block_rate") or 0.0) > float(manifest.get("max_clean_block_rate", 0.05)):
        errors.append("holdout clean_block_rate exceeds release threshold")
    if metrics.get("expected_failures"):
        errors.append("one or more frozen cases missed their expected decision")
    if int(metrics.get("unsafe_total") or 0) <= 0:
        errors.append("holdout must contain at least one unsafe case")
    if int(metrics.get("clean_total") or 0) <= 0:
        errors.append("holdout must contain at least one clean case")
    per_family = metrics.get("per_family") or {}
    for family in manifest.get("critical_block_families", []):
        family_counts = per_family.get(family) or {}
        total = sum(int(v) for v in family_counts.values())
        if total == 0:
            errors.append(f"critical family {family} is absent from the frozen holdout")
        elif int(family_counts.get("BLOCK", 0)) != total:
            errors.append(f"critical family {family} must be 100% BLOCK")
    return not errors, errors


def verify_release_evidence() -> dict:
    errors: list[str] = []
    if not (DATA.exists() and MANIFEST.exists() and RESULT.exists()):
        return {"verified": False, "holdout": "aqua-holdout-v17", "qualified": False, "metrics": {}, "errors": ["V17 release evidence is not sealed/executed yet"]}

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    actual_dataset = sha256(DATA)
    try:
        actual_semantics = semantic_fingerprint(manifest["semantic_files"])
    except (KeyError, FileNotFoundError) as exc:
        actual_semantics = ""
        errors.append(str(exc))
    try:
        actual_evaluator = semantic_fingerprint(manifest["evaluator_files"])
    except (KeyError, FileNotFoundError) as exc:
        actual_evaluator = ""
        errors.append(str(exc))

    if actual_dataset != manifest.get("dataset_sha256"):
        errors.append("holdout dataset hash differs from sealed manifest")
    if actual_semantics != manifest.get("semantic_fingerprint"):
        errors.append("semantic dependency closure changed after V17 was sealed")
    if actual_evaluator != manifest.get("evaluator_fingerprint"):
        errors.append("evaluation machinery changed after V17 was sealed")
    actual_lock = sha256(RUNTIME_LOCK) if RUNTIME_LOCK.exists() else ""
    if actual_lock != manifest.get("requirements_lock_sha256"):
        errors.append("runtime requirements lock changed after V17 was sealed")
    if platform.python_version() != manifest.get("python_version"):
        errors.append("Python runtime version differs from the sealed V17 environment")
    if int(manifest.get("case_count", -1)) != len(_load_cases()):
        errors.append("holdout case_count does not match sealed dataset")

    recomputed = run_cases(_load_cases())
    recomputed_view = _metric_view(recomputed)
    saved_view = _metric_view(result.get("metrics") or {})
    if saved_view != recomputed_view:
        errors.append("saved holdout result does not exactly match recomputation")
    errors.extend(_validate_metric_arithmetic(recomputed))
    errors.extend(_validate_manifest_counts(recomputed, manifest))

    qualified, gate_errors = _qualify(recomputed, manifest)
    errors.extend(gate_errors)
    if result.get("holdout") != manifest.get("holdout"):
        errors.append("saved result names a different holdout")
    if result.get("dataset_sha256") != manifest.get("dataset_sha256"):
        errors.append("saved result is bound to a different dataset")
    if result.get("semantic_fingerprint") != manifest.get("semantic_fingerprint"):
        errors.append("saved result is bound to different semantic code")
    if result.get("evaluator_fingerprint") != manifest.get("evaluator_fingerprint"):
        errors.append("saved result is bound to different evaluation machinery")
    if result.get("requirements_lock_sha256") != manifest.get("requirements_lock_sha256"):
        errors.append("saved result is bound to a different runtime lock")
    if result.get("qualified_against_declared_release_gates") is not qualified:
        errors.append("saved qualification flag disagrees with recomputed release gates")
    if list(result.get("qualification_errors") or []) != list(gate_errors):
        errors.append("saved qualification errors disagree with recomputed release gates")

    return {
        "verified": not errors,
        "holdout": manifest.get("holdout"),
        "disclosure": result.get("disclosure"),
        "dataset_sha256": actual_dataset,
        "semantic_fingerprint": actual_semantics,
        "evaluator_fingerprint": actual_evaluator,
        "requirements_lock_sha256": actual_lock,
        "python_version": platform.python_version(),
        "qualified": qualified,
        "executed_at_utc": result.get("executed_at_utc"),
        "metrics": {k: recomputed.get(k) for k in (
            "total", "unsafe_total", "unsafe_pass", "unsafe_block", "unsafe_review", "unsafe_source_review",
            "clean_total", "clean_pass", "clean_review", "clean_block", "clean_source_review",
            "clean_pass_rate", "clean_block_rate", "expected_pass_rate",
        )},
        "errors": errors,
    }
