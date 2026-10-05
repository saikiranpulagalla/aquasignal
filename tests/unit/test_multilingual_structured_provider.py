import json

import pytest

from signallock.contracts.extractor import HeuristicExtractor
from signallock.providers.openai_http import OpenAIResponsesProvider
from signallock.verification.engine import VerificationEngine


SOURCE = "Residents must shelter indoors until 6 PM. Do not enter the eastern underpass."


def _ev(text: str, quote: str):
    start = text.index(quote)
    return {"quote": quote, "start_char": start, "end_char": start + len(quote)}


def _contract_payload(text: str, *, language: str, safe: bool):
    if language == "hi":
        shelter_quote = "घर के अंदर शरण लेनी चाहिए"
        enter_quote = "पूर्वी अंडरपास में प्रवेश न करें" if safe else "पूर्वी अंडरपास में प्रवेश करें"
    else:
        shelter_quote = "ఇంట్లోనే ఆశ్రయం పొందాలి"
        enter_quote = "తూర్పు అండర్‌పాస్‌లోకి ప్రవేశించవద్దు" if safe else "తూర్పు అండర్‌పాస్‌లోకి ప్రవేశించండి"

    required = [{
        "type": "SHELTER", "verb": "shelter", "object": None, "destination": "indoors",
        "condition": None, "deadline": "6 PM", "negated": False, "evidence": _ev(text, shelter_quote),
    }]
    prohibited = []
    if safe:
        prohibited.append({
            "type": "AVOID", "verb": "enter", "object": "the eastern underpass", "destination": None,
            "condition": None, "deadline": None, "negated": True, "evidence": _ev(text, enter_quote),
        })
    else:
        required.append({
            "type": "AVOID", "verb": "enter", "object": "the eastern underpass", "destination": None,
            "condition": None, "deadline": None, "negated": False, "evidence": _ev(text, enter_quote),
        })

    return {
        "schema_version": "1.0", "language": language, "hazard": None,
        "audience": ["residents"], "affected_areas": [],
        "required_actions": required, "prohibited_actions": prohibited,
        "urgency": "Unknown", "severity": "Unknown", "certainty": "Unknown",
        "effective_at": None, "expires_at": None, "quantities": [], "exceptions": [],
        "unresolved_operational_text": [], "source_id": None,
    }


def _response(payload):
    return {"output": [{"content": [{"type": "output_text", "text": json.dumps(payload, ensure_ascii=False)}]}]}


@pytest.mark.asyncio
@pytest.mark.parametrize("language,text", [
    ("hi", "निवासियों को शाम 6 बजे तक घर के अंदर शरण लेनी चाहिए। पूर्वी अंडरपास में प्रवेश न करें।"),
    ("te", "నివాసితులు సాయంత్రం 6 గంటల వరకు ఇంట్లోనే ఆశ్రయం పొందాలి. తూర్పు అండర్‌పాస్‌లోకి ప్రవేశించవద్దు."),
])
async def test_native_evidence_with_canonical_slots_can_pass(language, text, monkeypatch):
    provider = OpenAIResponsesProvider(api_key="test")
    payload = _contract_payload(text, language=language, safe=True)
    async def fake_request(self, _payload): return _response(payload)
    monkeypatch.setattr(OpenAIResponsesProvider, "_request", fake_request)
    candidate = await provider.extract_contract(text, language=language, source_id="candidate")
    assert candidate.language == language
    # Evidence remains native while semantic slots are canonical English.
    assert candidate.required_actions[0].evidence.quote in text
    assert candidate.required_actions[0].verb == "shelter"
    assert candidate.required_actions[0].destination == "indoors"
    source = HeuristicExtractor().extract(SOURCE, source_id="source")
    result = VerificationEngine().verify(source, candidate)
    assert result.decision.value == "PASS"


@pytest.mark.asyncio
@pytest.mark.parametrize("language,text", [
    ("hi", "निवासियों को शाम 6 बजे तक घर के अंदर शरण लेनी चाहिए। पूर्वी अंडरपास में प्रवेश करें।"),
    ("te", "నివాసితులు సాయంత్రం 6 గంటల వరకు ఇంట్లోనే ఆశ్రయం పొందాలి. తూర్పు అండర్‌పాస్‌లోకి ప్రవేశించండి."),
])
async def test_multilingual_action_reversal_blocks(language, text, monkeypatch):
    provider = OpenAIResponsesProvider(api_key="test")
    payload = _contract_payload(text, language=language, safe=False)
    async def fake_request(self, _payload): return _response(payload)
    monkeypatch.setattr(OpenAIResponsesProvider, "_request", fake_request)
    candidate = await provider.extract_contract(text, language=language, source_id="candidate")
    source = HeuristicExtractor().extract(SOURCE, source_id="source")
    result = VerificationEngine().verify(source, candidate)
    assert result.decision.value == "BLOCK"
