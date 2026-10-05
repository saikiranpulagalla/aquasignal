from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
import platform
import subprocess
from importlib.metadata import PackageNotFoundError, version as installed_version

from aquasignal.evaluation.runner import run_cases
from aquasignal.evaluation.evidence import verify_release_evidence

V17_MANIFEST = ROOT / "data" / "aqua" / "holdout_v17.manifest.json"


def expected_python_version() -> str:
    """Read the qualified runtime from the frozen V17 manifest."""
    try:
        value = json.loads(V17_MANIFEST.read_text(encoding="utf-8"))["python_version"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read sealed V17 Python runtime from {V17_MANIFEST.name}: {exc}") from exc
    if not isinstance(value, str) or not value:
        raise RuntimeError("sealed V17 Python runtime is invalid")
    return value


def _verify_python_preflight() -> list[str]:
    expected = expected_python_version()
    actual = platform.python_version()
    if actual != expected:
        return [
            f"expected Python {expected}, found {actual}.",
            "Qualification tests were not executed because this runtime is outside the sealed V17 environment.",
        ]
    return []


def _verify_lock(path: Path) -> list[str]:
    errors: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            errors.append(f"{path.name}: non-exact requirement {line!r}")
            continue
        name, expected = line.split("==", 1)
        try:
            actual = installed_version(name.strip())
        except PackageNotFoundError:
            errors.append(f"{path.name}: {name.strip()} is not installed")
            continue
        if actual != expected.strip():
            errors.append(f"{path.name}: {name.strip()} expected {expected.strip()} but found {actual}")
    return errors


def main() -> int:
    print("[0/5] Sealed Python runtime preflight")
    try:
        runtime_errors = _verify_python_preflight()
    except RuntimeError as exc:
        print("RELEASE GATE FAILED: " + str(exc), file=sys.stderr)
        print("Qualification tests were not executed.", file=sys.stderr)
        return 2
    if runtime_errors:
        for error in runtime_errors:
            print("RELEASE GATE FAILED: " + error, file=sys.stderr)
        return 2

    print("[1/5] Locked Python environment")
    lock_errors = _verify_lock(ROOT / "requirements-dev.lock")
    if lock_errors:
        for error in lock_errors:
            print("RELEASE GATE FAILED: " + error, file=sys.stderr)
        return 2

    print("[2/5] AquaSignal semantic/API tests")
    aqua = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/aqua"], check=False)
    if aqua.returncode:
        return aqua.returncode

    print("[3/5] Full inherited + Aqua regression suite")
    full = subprocess.run([sys.executable, "-m", "pytest", "-q"], check=False)
    if full.returncode:
        return full.returncode

    print("[4/5] Aqua DEV benchmark gates")
    result = run_cases()
    print(json.dumps({k: result[k] for k in (
        "total", "unsafe_total", "clean_total", "unsafe_pass", "unsafe_block",
        "unsafe_review", "clean_pass", "clean_block", "clean_review",
        "unsafe_pass_rate", "clean_pass_rate", "clean_block_rate",
    )}, indent=2))
    failures = []
    if result["unsafe_pass"] != 0:
        failures.append("unsafe_pass must equal 0")
    if result["clean_pass_rate"] < 0.80:
        failures.append("clean_pass_rate must be >= 0.80")
    if result["clean_block_rate"] > 0.05:
        failures.append("clean_block_rate must be <= 0.05")
    if failures:
        print("RELEASE GATE FAILED: " + "; ".join(failures), file=sys.stderr)
        return 2

    print("[5/5] Frozen Aqua release evidence recomputation")
    holdout = verify_release_evidence()
    print(json.dumps({
        "holdout": holdout["holdout"],
        "verified": holdout["verified"],
        "qualified": holdout["qualified"],
        "metrics": holdout["metrics"],
        "errors": holdout["errors"],
    }, indent=2))
    if not holdout["verified"]:
        print("RELEASE GATE FAILED: frozen holdout evidence is stale or unqualified", file=sys.stderr)
        return 2

    print("RELEASE GATE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
