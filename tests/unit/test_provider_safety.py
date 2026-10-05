import json

import pytest

from signallock.providers.openai_http import OpenAIResponsesProvider, ProviderError


class FakeProvider(OpenAIResponsesProvider):
    response_text = ""

    async def _request(self, payload):
        return {"output": [{"content": [{"type": "output_text", "text": self.response_text}]}]}


@pytest.mark.asyncio
async def test_live_extraction_rejects_fabricated_p0_provenance():
    p = FakeProvider(api_key="test")
    p.response_text = json.dumps({
        "schema_version": "1.0",
        "language": "en",
        "hazard": None,
        "audience": [],
        "affected_areas": [],
        "required_actions": [{
            "type": "EVACUATE",
            "verb": "evacuate",
            "object": None,
            "destination": None,
            "condition": None,
            "deadline": None,
            "negated": False,
            "evidence": {"quote": "THIS DOES NOT EXIST", "start_char": 0, "end_char": 19},
        }],
        "prohibited_actions": [],
        "urgency": "Unknown",
        "severity": "Unknown",
        "certainty": "Unknown",
        "effective_at": None,
        "expires_at": None,
        "quantities": [],
        "exceptions": [],
        "source_id": None,
    })
    with pytest.raises(ProviderError, match="provenance"):
        await p.extract_contract("Shelter indoors.", language="en")


@pytest.mark.asyncio
async def test_live_extraction_requires_p0_provenance():
    p = FakeProvider(api_key="test")
    p.response_text = json.dumps({
        "schema_version": "1.0",
        "language": "en",
        "hazard": None,
        "audience": [],
        "affected_areas": [],
        "required_actions": [{
            "type": "SHELTER",
            "verb": "shelter",
            "object": None,
            "destination": "indoors",
            "condition": None,
            "deadline": None,
            "negated": False,
            "evidence": None,
        }],
        "prohibited_actions": [],
        "urgency": "Unknown",
        "severity": "Unknown",
        "certainty": "Unknown",
        "effective_at": None,
        "expires_at": None,
        "quantities": [],
        "exceptions": [],
        "source_id": None,
    })
    with pytest.raises(ProviderError, match="provenance"):
        await p.extract_contract("Shelter indoors.", language="en")


@pytest.mark.asyncio
async def test_sms_postcondition_is_enforced():
    p = FakeProvider(api_key="test")
    p.response_text = "X" * 500
    with pytest.raises(ProviderError, match="character limit"):
        await p.transform("alert", mode="sms", max_chars=80)

@pytest.mark.asyncio
async def test_unique_exact_quote_can_repair_bad_offsets():
    p = FakeProvider(api_key="test")
    text = "Alert: Shelter indoors now."
    quote = "Shelter indoors"
    p.response_text = json.dumps({
        "schema_version": "1.0",
        "language": "en",
        "hazard": None,
        "audience": [],
        "affected_areas": [],
        "required_actions": [{
            "type": "SHELTER", "verb": "shelter", "object": None, "destination": "indoors",
            "condition": None, "deadline": None, "negated": False,
            "evidence": {"quote": quote, "start_char": 0, "end_char": len(quote)},
        }],
        "prohibited_actions": [], "urgency": "Unknown", "severity": "Unknown", "certainty": "Unknown",
        "effective_at": None, "expires_at": None, "quantities": [], "exceptions": [], "source_id": None,
    })
    contract = await p.extract_contract(text, language="en")
    ev = contract.required_actions[0].evidence
    assert ev is not None
    assert text[ev.start_char:ev.end_char] == quote
