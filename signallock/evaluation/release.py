from __future__ import annotations

import hashlib
import json
import subprocess
import os
from pathlib import Path


RUNTIME_PATHS = ("signallock", "apps", "scripts", "web", "pyproject.toml", "Makefile")
RELEASE_MANIFEST = "RELEASE_MANIFEST.json"


class ReleaseIdentityError(RuntimeError):
    pass


def project_version(root: Path) -> str:
    """Read the canonical application version from pyproject.toml."""
    import tomllib
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = str(data.get("project", {}).get("version", "")).strip()
    if not version:
        raise ReleaseIdentityError("pyproject.toml is missing project.version")
    return version


def _runtime_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for item in RUNTIME_PATHS:
        path = root / item
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(
                p for p in path.rglob("*")
                if p.is_file()
                and "__pycache__" not in p.parts
                and p.suffix not in {".pyc", ".pyo"}
            )
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def runtime_tree_sha256(root: Path) -> str:
    h = hashlib.sha256()
    for path in _runtime_files(root):
        rel = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes()
        h.update(len(rel).to_bytes(4, "big")); h.update(rel)
        h.update(len(data).to_bytes(8, "big")); h.update(data)
    return h.hexdigest()


def resolve_release_identity(root: Path) -> dict:
    """Return a clean immutable identity from Git or a packaged release manifest."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--", *RUNTIME_PATHS], cwd=root, text=True
        ).strip()
        return {
            "source": "git",
            "identity": commit,
            "clean": not bool(dirty),
            "runtime_tree_sha256": runtime_tree_sha256(root),
            "error": None if not dirty else "runtime code is dirty",
        }
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    manifest_path = root / RELEASE_MANIFEST
    if not manifest_path.exists():
        return {
            "source": "none", "identity": None, "clean": False,
            "runtime_tree_sha256": runtime_tree_sha256(root),
            "error": "no Git checkout and no RELEASE_MANIFEST.json",
        }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "source": "release-manifest", "identity": None, "clean": False,
            "runtime_tree_sha256": runtime_tree_sha256(root),
            "error": f"invalid release manifest: {exc}",
        }
    actual = runtime_tree_sha256(root)
    expected = manifest.get("runtime_tree_sha256")
    identity = manifest.get("source_commit") or manifest.get("release_id")
    internally_consistent = bool(identity and expected and expected == actual)
    trusted = os.getenv("SIGNALLOCK_TRUSTED_RUNTIME_SHA256", "").strip().casefold()
    externally_trusted = bool(trusted and expected and trusted == str(expected).casefold())
    clean = internally_consistent and externally_trusted
    if not internally_consistent:
        error = "release manifest runtime tree hash mismatch or identity missing"
    elif not externally_trusted:
        error = "packaged release is internally consistent but lacks external trust anchor SIGNALLOCK_TRUSTED_RUNTIME_SHA256"
    else:
        error = None
    return {
        "source": "release-manifest",
        "identity": identity,
        "clean": clean,
        "internally_consistent": internally_consistent,
        "externally_trusted": externally_trusted,
        "runtime_tree_sha256": actual,
        "error": error,
    }


def write_release_manifest(root: Path, *, source_commit: str | None, release_id: str) -> dict:
    manifest = {
        "kind": "SignalLock immutable packaged release identity",
        "release_id": release_id,
        "source_commit": source_commit,
        "runtime_tree_sha256": runtime_tree_sha256(root),
    }
    (root / RELEASE_MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
