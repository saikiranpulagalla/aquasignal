from pathlib import Path


APP = Path('web/app.js').read_text(encoding='utf-8')


def test_web_verifies_against_frozen_source_contract():
    assert "'/api/verify-contract'" in APP
    assert "getFrozenSourceContract" in APP
    assert "source_contract:sourceContract" in APP


def test_web_invalidates_source_contract_on_authority_change():
    assert "source.addEventListener('input',invalidateSourceContract)" in APP
    assert "document.getElementById('provider').addEventListener('change',invalidateSourceContract)" in APP


def test_web_no_longer_uses_reextract_both_sides_endpoint():
    assert "fetch('/api/verify'" not in APP
