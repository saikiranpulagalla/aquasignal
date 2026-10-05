from pathlib import Path

INDEX = (Path(__file__).parents[2] / "web" / "index.html").read_text(encoding="utf-8")
APP = (Path(__file__).parents[2] / "web" / "app.js").read_text(encoding="utf-8")


def test_no_inline_event_handlers_and_csp_present():
    assert "onclick=" not in INDEX
    assert "Content-Security-Policy" in INDEX
    assert "script-src 'self'" in INDEX


def test_translate_button_is_exposed():
    assert 'id="translateBtn"' in INDEX
    assert "generateTransform('translate')" in APP


def test_contract_dynamic_fields_are_escaped():
    assert "map(x=>esc(`" in APP
