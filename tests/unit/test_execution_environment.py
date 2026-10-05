from copy import deepcopy
from pathlib import Path

import pytest

from signallock.evaluation.environment import (
    execution_environment, environment_sha256, qualification_environment_errors,
)
from signallock.evaluation.holdout import HoldoutError, _runtime_binding, verify_v7_runtime_binding


def test_environment_capture_and_fingerprint_are_stable():
    first = execution_environment()
    assert first == execution_environment()
    assert environment_sha256(first) == environment_sha256(dict(reversed(list(first.items()))))
    other = deepcopy(first)
    other["dependencies"] = dict(reversed(list(other["dependencies"].items())))
    assert environment_sha256(first) == environment_sha256(other)


@pytest.mark.parametrize("field", ["python", "dependency"])
def test_critical_environment_change_changes_fingerprint(field):
    first = execution_environment()
    changed = deepcopy(first)
    if field == "python":
        changed["python"]["version"] = "0.0.0"
    else:
        changed["dependencies"]["pydantic"] = "0.0.0"
    assert environment_sha256(first) != environment_sha256(changed)


@pytest.mark.parametrize("missing", [False, True])
def test_strict_binding_requires_current_environment(missing):
    binding = _runtime_binding(provider="openai", model="unit-test-model")
    if missing:
        binding.pop("execution_environment")
    else:
        binding["execution_environment"]["python"]["version"] = "0.0.0"
    with pytest.raises(HoldoutError, match="fingerprint|environment"):
        verify_v7_runtime_binding({"strict_v7": True, "runtime_binding": binding}, provider="openai", model="unit-test-model")


def test_declared_constraints_are_checked_without_assuming_this_machine_is_compliant(tmp_path):
    descriptor = execution_environment()
    descriptor["python"]["version"] = "3.12.0"
    descriptor["dependencies"]["pydantic"] = "2.0.0"
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.12"\ndependencies = ["pydantic>=2.13,<3"]\n', encoding="utf-8"
    )
    assert any("pydantic" in e for e in qualification_environment_errors(tmp_path, descriptor))
    descriptor["dependencies"]["pydantic"] = "2.13.0"
    assert qualification_environment_errors(tmp_path, descriptor) == []
    descriptor["python"]["version"] = "3.11.0"
    assert any("Python" in e for e in qualification_environment_errors(tmp_path, descriptor))


def test_missing_critical_distribution_is_reported():
    descriptor = execution_environment()
    descriptor["dependencies"]["httpx"] = None
    assert any("httpx" in e for e in qualification_environment_errors(descriptor=descriptor))
