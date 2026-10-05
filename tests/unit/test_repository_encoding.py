"""A static portability check, not a semantic or security behavior test."""
import ast
from pathlib import Path


def test_repository_path_text_io_declares_utf8():
    root = Path(__file__).resolve().parents[2]
    missing = []
    for directory in ("tests", "scripts", "signallock", "apps"):
        for path in (root / directory).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in {"read_text", "write_text"}:
                    continue
                encoding = next((k.value for k in node.keywords if k.arg == "encoding"), None)
                if not isinstance(encoding, ast.Constant) or encoding.value != "utf-8":
                    missing.append(f"{path.relative_to(root)}:{node.lineno}")
    assert not missing, "Repository text I/O needs explicit UTF-8: " + ", ".join(missing)
