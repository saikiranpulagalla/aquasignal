import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _release_gate_module():
    spec = importlib.util.spec_from_file_location("release_gate_under_test", ROOT / "scripts" / "release_gate.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mismatched_python_stops_before_any_release_gate_subprocess(monkeypatch, capsys):
    gate = _release_gate_module()
    monkeypatch.setattr(gate.platform, "python_version", lambda: "0.0.0")
    monkeypatch.setattr(gate, "expected_python_version", lambda: "3.13.5")

    def subprocess_must_not_run(*args, **kwargs):
        raise AssertionError("release-gate subprocess execution must not begin after runtime mismatch")

    monkeypatch.setattr(gate.subprocess, "run", subprocess_must_not_run)

    assert gate.main() == 2
    captured = capsys.readouterr()
    assert "expected Python 3.13.5" in captured.err
    assert "found 0.0.0" in captured.err
    assert "Qualification tests were not executed" in captured.err
