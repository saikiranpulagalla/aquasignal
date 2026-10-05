import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from signallock.contracts.extractor import HeuristicExtractor
from signallock.contracts.schema import Hazard, SafetyContract
from signallock.providers.openai_http import OpenAIResponsesProvider
from signallock.verification.engine import VerificationEngine


E = HeuristicExtractor()
V = VerificationEngine()
CLIENT = TestClient(app)

UNSAFE = [
    ("Residents in the eastern flood zone must evacuate. Residents in the western flood zone must shelter indoors.", "Residents in the eastern flood zone must shelter indoors. Residents in the western flood zone must evacuate."),
    ("Residents must evacuate. Visitors must shelter indoors.", "Residents must shelter indoors. Visitors must evacuate."),
    ("In the eastern flood zone, avoid roads with more than 30 cm of water. In the western flood zone, avoid roads with more than 10 cm of water.", "In the eastern flood zone, avoid roads with more than 10 cm of water. In the western flood zone, avoid roads with more than 30 cm of water."),
    ("Evacuate, except emergency personnel. Shelter indoors, except visitors.", "Evacuate, except visitors. Shelter indoors, except emergency personnel."),
    ("If officials order it, residents evacuate immediately.", "Residents evacuate immediately."),
    ("Residents are not required to evacuate.", "Residents are required to evacuate."),
    ("Residents may shelter indoors.", "Residents must shelter indoors."),
    ("Residents must shelter indoors.", "Non‑residents must shelter indoors."),
    ("Residents must evacuate before 6 PM.", "Residents must evacuate after 6 PM."),
    ("Turn off the gas supply, then evacuate.", "Evacuate, then turn off the gas supply."),
    ("Residents should evacuate or shelter indoors.", "Residents should evacuate and shelter indoors."),
    ("Residents must shelter indoors until 6 PM. Visitors must shelter indoors until 8 PM.", "Residents must shelter indoors until 6 PM. Visitors must shelter indoors until 10 PM."),
]

SAFE = [
    ("Residents must evacuate if water reaches more than 30 cm.", "Residents must evacuate if water reaches more than 0.3 m."),
    ("Residents must evacuate if officials order it.", "Residents must evacuate if ordered by officials."),
    ("Avoid the road except for emergency personnel.", "Avoid the road unless you are emergency personnel."),
    ("Drivers must avoid roads.", "Motorists must avoid roads."),
]


def _decision(source: str, candidate: str) -> str:
    return V.verify(E.extract(source), E.extract(candidate)).decision.value


def test_second_order_unsafe_relational_cases_never_pass():
    results = [_decision(s, c) for s, c in UNSAFE]
    assert "PASS" not in results


def test_second_order_safe_paraphrases_remain_usable():
    assert [_decision(s, c) for s, c in SAFE] == ["PASS"] * len(SAFE)


def _cap(*, status="Actual", msg="Alert", scope="Public", instruction="Residents must shelter indoors.", extra_info="", area_extra="", sent="2026-09-10T12:00:00+05:30", identifier="A1", sender="alerts.example", namespace=True, references="", addresses=""):
    ns=' xmlns="urn:oasis:names:tc:emergency:cap:1.2"' if namespace else ""
    refs=f"<references>{references}</references>" if references else ""
    addrs=f"<addresses>{addresses}</addresses>" if addresses else ""
    return f'''<alert{ns}><identifier>{identifier}</identifier><sender>{sender}</sender><sent>{sent}</sent><status>{status}</status><msgType>{msg}</msgType><scope>{scope}</scope>{refs}{addrs}<info><language>en</language><category>Met</category><event>Flood</event><urgency>Immediate</urgency><severity>Severe</severity><certainty>Likely</certainty><instruction>{instruction}</instruction><area><areaDesc>East Zone</areaDesc>{area_extra}</area></info>{extra_info}</alert>'''


def _cap_never_pass(candidate: str):
    r = CLIENT.post("/api/verify-cap", json={"source_xml": _cap(), "candidate_xml": candidate})
    assert r.status_code != 200 or r.json().get("decision") != "PASS"


def test_material_cap_envelope_and_geospatial_changes_never_pass():
    extra = '<info><language>en</language><category>Met</category><event>Flood</event><urgency>Immediate</urgency><severity>Severe</severity><certainty>Likely</certainty><instruction>Residents must evacuate immediately.</instruction><area><areaDesc>West Zone</areaDesc></area></info>'
    candidates = [
        _cap(status="Test"),
        _cap(msg="Cancel"),
        _cap(scope="Private"),
        _cap(sender="evil.example"),
        _cap(sent="2026-09-10T13:00:00+05:30"),
        _cap(area_extra="<polygon>10,10 10,11 11,11 10,10</polygon>"),
        _cap(extra_info=extra),
    ]
    for candidate in candidates:
        _cap_never_pass(candidate)


def test_forged_client_authority_is_rejected():
    source = "Residents must shelter indoors."
    contract = E.extract(source, source_id="source").model_dump(mode="json")
    contract["audience"] = ["visitors"]
    action = contract["required_actions"][0]
    action["type"] = "EVACUATE"; action["verb"] = "evacuate"; action["destination"] = None
    r = CLIENT.post("/api/verify-contract", json={
        "source_text": source, "source_contract": contract,
        "candidate_text": "Visitors must evacuate.", "candidate_language": "en", "provider": "heuristic",
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_exact_native_quote_cannot_prove_false_canonical_semantics():
    candidate_text = "निवासी तुरंत बाहर निकलें।"
    payload = {
        "schema_version":"1.0","language":"hi","hazard":None,"audience":["residents"],"affected_areas":[],
        "required_actions":[{"type":"SHELTER","verb":"shelter","object":None,"destination":"indoors","condition":None,"deadline":None,"negated":False,
                             "evidence":{"quote":candidate_text,"start_char":0,"end_char":len(candidate_text)}}],
        "prohibited_actions":[],"urgency":"Unknown","severity":"Unknown","certainty":"Unknown","effective_at":None,"expires_at":None,
        "quantities":[],"exceptions":[],"unresolved_operational_text":[],"source_id":None,
    }
    class Fake(OpenAIResponsesProvider):
        async def _request(self, _payload):
            return {"output":[{"content":[{"type":"output_text","text":json.dumps(payload,ensure_ascii=False)}]}]}
    candidate = await Fake(api_key="x").extract_contract(candidate_text, language="hi", source_id="cand")
    result = V.verify(E.extract("Residents must shelter indoors."), candidate)
    assert result.decision.value != "PASS"
    assert candidate.unresolved_operational_text


def test_material_hazard_description_change_never_passes():
    result = V.verify(
        SafetyContract(hazard=Hazard(type="flood", description="dam failure imminent")),
        SafetyContract(hazard=Hazard(type="flood", description="minor drainage issue")),
    )
    assert result.decision.value != "PASS"


def test_mutually_exclusive_same_scope_source_is_not_certified_pass():
    result = V.verify(
        E.extract("Residents must shelter indoors. Residents must evacuate immediately."),
        E.extract("Residents must shelter indoors. Residents must evacuate immediately."),
    )
    assert result.decision.value == "REVIEW"


def test_strict_cap_profile_rejects_namespace_and_timezone_shortcuts():
    assert CLIENT.post("/api/cap", json={"xml": _cap(namespace=False)}).status_code == 422
    assert CLIENT.post("/api/cap", json={"xml": _cap(sent="2026-09-10T12:00:00")}).status_code == 422
    assert CLIENT.post("/api/cap", json={"xml": _cap(sent="2026-09-10T12:00:00Z")}).status_code == 422
