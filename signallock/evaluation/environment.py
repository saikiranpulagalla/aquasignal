"""Deterministic environment provenance for strict qualification."""
from __future__ import annotations

import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import ssl
import tomllib

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

ROOT = Path(__file__).resolve().parents[2]
CRITICAL_DISTRIBUTIONS = ("pydantic", "pydantic-core", "fastapi", "starlette", "uvicorn", "httpx", "httpcore", "anyio", "h11", "defusedxml", "packaging")


def execution_environment(root: Path = ROOT) -> dict:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    dependencies = {}
    for name in CRITICAL_DISTRIBUTIONS:
        try:
            dependencies[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            dependencies[name] = None
    return {"descriptor_version": 1, "project_version": project["version"], "python": {"implementation": platform.python_implementation(), "version": platform.python_version()}, "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()}, "openssl": ssl.OPENSSL_VERSION, "dependencies": dependencies}


def environment_sha256(descriptor: dict) -> str:
    canonical = json.dumps(descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def qualification_environment_errors(root: Path = ROOT, descriptor: dict | None = None) -> list[str]:
    descriptor = execution_environment(root) if descriptor is None else descriptor
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    errors = []
    python_version = descriptor["python"]["version"]
    if python_version not in SpecifierSet(project["requires-python"]):
        errors.append(f"Python {python_version} does not satisfy {project['requires-python']}")
    versions = descriptor["dependencies"]
    for name in CRITICAL_DISTRIBUTIONS:
        if not versions.get(name):
            errors.append(f"qualification-critical dependency {name} is missing")
    for raw in project.get("dependencies", []):
        requirement = Requirement(raw)
        installed = versions.get(requirement.name)
        if installed is None:
            errors.append(f"declared dependency {requirement.name} is missing from qualification environment")
        elif installed not in requirement.specifier:
            errors.append(f"{requirement.name} {installed} does not satisfy {requirement.specifier}")
    return errors


def require_qualification_environment(root: Path = ROOT) -> dict:
    descriptor = execution_environment(root)
    errors = qualification_environment_errors(root, descriptor)
    if errors:
        raise ValueError("Qualification environment is noncompliant: " + "; ".join(errors))
    return descriptor
