from __future__ import annotations

import asyncio
import json
import subprocess
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from apps.api.main import app
from signallock.contracts.extractor import HeuristicExtractor
from signallock.contracts.schema import Hazard, SafetyContract
from signallock.evaluation.holdout import HoldoutError, seal_v7_holdout_strict
from signallock.evaluation.v7 import V7_REQUIRED_FAULT_CLASSES, evaluate_v7_gate
from signallock.providers.openai_http import OpenAIResponsesProvider
from signallock.verification.engine import VerificationEngine

E = HeuristicExtractor(); V = VerificationEngine(); client = TestClient(app)
OUT = ROOT / "data/results/second_order_audit.json"

UNSAFE = [
    ("action_area_binding_swap", "Residents in the eastern flood zone must evacuate. Residents in the western flood zone must shelter indoors.", "Residents in the eastern flood zone must shelter indoors. Residents in the western flood zone must evacuate."),
    ("action_audience_binding_swap", "Residents must evacuate. Visitors must shelter indoors.", "Residents must shelter indoors. Visitors must evacuate."),
    ("quantity_area_binding_swap", "In the eastern flood zone, avoid roads with more than 30 cm of water. In the western flood zone, avoid roads with more than 10 cm of water.", "In the eastern flood zone, avoid roads with more than 10 cm of water. In the western flood zone, avoid roads with more than 30 cm of water."),
    ("exception_action_binding_swap", "Evacuate, except emergency personnel. Shelter indoors, except visitors.", "Evacuate, except visitors. Shelter indoors, except emergency personnel."),
    ("leading_condition_removed", "If officials order it, residents evacuate immediately.", "Residents evacuate immediately."),
    ("not_required_to_required", "Residents are not required to evacuate.", "Residents are required to evacuate."),
    ("permissive_to_mandatory", "Residents may shelter indoors.", "Residents must shelter indoors."),
    ("unicode_nonresident_scope", "Residents must shelter indoors.", "Non‑residents must shelter indoors."),
    ("deadline_relation_before_after", "Residents must evacuate before 6 PM.", "Residents must evacuate after 6 PM."),
    ("action_sequence_reversed", "Turn off the gas supply, then evacuate.", "Evacuate, then turn off the gas supply."),
    ("choice_or_to_and", "Residents should evacuate or shelter indoors.", "Residents should evacuate and shelter indoors."),
    ("dedupe_hides_second_directive_change", "Residents must shelter indoors until 6 PM. Visitors must shelter indoors until 8 PM.", "Residents must shelter indoors until 6 PM. Visitors must shelter indoors until 10 PM."),
]
SAFE = [
    ("condition_unit_conversion", "Residents must evacuate if water reaches more than 30 cm.", "Residents must evacuate if water reaches more than 0.3 m."),
    ("condition_paraphrase", "Residents must evacuate if officials order it.", "Residents must evacuate if ordered by officials."),
    ("exception_paraphrase", "Avoid the road except for emergency personnel.", "Avoid the road unless you are emergency personnel."),
    ("audience_synonym", "Drivers must avoid roads.", "Motorists must avoid roads."),
]


def text_case(name, source, candidate):
    result = V.verify(E.extract(source), E.extract(candidate))
    return {"name": name, "decision": result.decision.value, "critical_failures": result.critical_failures, "warnings": result.warnings}


def cap(*, status="Actual", msg="Alert", scope="Public", instruction="Residents must shelter indoors.", extra_info="", area_extra="", sent="2026-09-10T12:00:00+05:30", identifier="A1", sender="alerts.example", namespace=True):
    ns=' xmlns="urn:oasis:names:tc:emergency:cap:1.2"' if namespace else ""
    return f'''<alert{ns}><identifier>{identifier}</identifier><sender>{sender}</sender><sent>{sent}</sent><status>{status}</status><msgType>{msg}</msgType><scope>{scope}</scope><info><language>en</language><category>Met</category><event>Flood</event><urgency>Immediate</urgency><severity>Severe</severity><certainty>Likely</certainty><instruction>{instruction}</instruction><area><areaDesc>East Zone</areaDesc>{area_extra}</area></info>{extra_info}</alert>'''


def cap_case(name, candidate):
    r = client.post("/api/verify-cap", json={"source_xml": cap(), "candidate_xml": candidate})
    body = r.json()
    return {"name": name, "status_code": r.status_code, "decision": body.get("decision"), "safe": r.status_code != 200 or body.get("decision") != "PASS"}


async def model_semantic_lie():
    text = "निवासी तुरंत बाहर निकलें।"
    payload = {
        "schema_version":"1.0","language":"hi","hazard":None,"audience":["residents"],"affected_areas":[],
        "required_actions":[{"type":"SHELTER","verb":"shelter","object":None,"destination":"indoors","condition":None,"deadline":None,"negated":False,"evidence":{"quote":text,"start_char":0,"end_char":len(text)}}],
        "prohibited_actions":[],"urgency":"Unknown","severity":"Unknown","certainty":"Unknown","effective_at":None,"expires_at":None,
        "quantities":[],"exceptions":[],"unresolved_operational_text":[],"source_id":None,
    }
    class Fake(OpenAIResponsesProvider):
        async def _request(self, _payload):
            return {"output":[{"content":[{"type":"output_text","text":json.dumps(payload, ensure_ascii=False)}]}]}
    candidate = await Fake(api_key="x").extract_contract(text, language="hi", source_id="candidate")
    result = V.verify(E.extract("Residents must shelter indoors."), candidate)
    return {"decision": result.decision.value, "unresolved": candidate.unresolved_operational_text, "safe": result.decision.value != "PASS"}


def authority_tamper():
    source = "Residents must shelter indoors."
    contract = E.extract(source, source_id="source").model_dump(mode="json")
    contract["audience"] = ["visitors"]
    a = contract["required_actions"][0]; a["type"]="EVACUATE"; a["verb"]="evacuate"; a["destination"]=None
    r = client.post("/api/verify-contract", json={"source_text":source,"source_contract":contract,"candidate_text":"Visitors must evacuate.","candidate_language":"en","provider":"heuristic"})
    return {"status_code":r.status_code,"decision":r.json().get("decision"),"safe":r.status_code==422}


def holdout_gaming():
    source = "Residents must shelter indoors."
    contract = E.extract(source, source_id="authority").model_dump(mode="json")
    rows=[]
    for lang in ("hi","te"):
        for i in range(12):
            rows.append({"case_id":f"{lang}-{i}","source_text":source,"source_language":"en","source_contract":contract,
                         "candidate_text":"Residents must shelter indoors.","candidate_language":lang,
                         "expected_decision":"PASS" if i<4 else "BLOCK","human_reviewed":True,
                         "reviewer_id":"r1","second_reviewer_id":"r2","reviewed_at":"2026-09-12T10:00:00+05:30",
                         "source_reference":"audit","fault_class":"clean" if i<4 else "modality"})
    with tempfile.TemporaryDirectory() as d:
        d=Path(d); inp=d/"in.jsonl"
        inp.write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in rows),encoding="utf-8")
        try:
            seal_v7_holdout_strict(inp,d/"out.jsonl",d/"manifest.json",schema_version="1",verifier_version="v",extractor_version="e",prompt_version="p",code_commit="abc",provider="openai",model="gpt-test")
            refused=False; error=None
        except HoldoutError as exc:
            refused=True; error=str(exc)
    numeric_only={"total":32,"dangerous_pass_rate":0.0,"clean_pass_rate":0.9,"clean_block_rate":0.0,"exact_decision_accuracy":0.94,
                  "by_language":{"hi":{"total":16,"expected_pass_total":6,"expected_block_total":10,"dangerous_pass_rate":0.0,"clean_pass_rate":0.83},"te":{"total":16,"expected_pass_total":6,"expected_block_total":10,"dangerous_pass_rate":0.0,"clean_pass_rate":0.83}}}
    return {"strict_sealer_refused":refused,"error":error,"numeric_only_gate":evaluate_v7_gate(numeric_only)}


def main():
    unsafe=[text_case(*x) for x in UNSAFE]; safe=[text_case(*x) for x in SAFE]
    extra='<info><language>en</language><category>Met</category><event>Flood</event><urgency>Immediate</urgency><severity>Severe</severity><certainty>Likely</certainty><instruction>Residents must evacuate immediately.</instruction><area><areaDesc>West Zone</areaDesc></area></info>'
    caps=[cap_case("status_actual_to_test",cap(status="Test")),cap_case("msgtype_alert_to_cancel",cap(msg="Cancel")),cap_case("scope_public_to_private",cap(scope="Private")),cap_case("sender_changed",cap(sender="evil.example")),cap_case("sent_changed",cap(sent="2026-09-10T13:00:00+05:30")),cap_case("polygon_changed",cap(area_extra="<polygon>10,10 10,11 11,11 10,10</polygon>")),cap_case("candidate_extra_info",cap(extra_info=extra))]
    hazard=V.verify(SafetyContract(hazard=Hazard(type="flood",description="dam failure imminent")),SafetyContract(hazard=Hazard(type="flood",description="minor drainage issue")))
    conflict=text_case("source_conflict","Residents must shelter indoors. Residents must evacuate immediately.","Residents must shelter indoors. Residents must evacuate immediately.")
    preflight=subprocess.run([sys.executable,"scripts/run_v7_preflight.py"],cwd=ROOT,capture_output=True,text=True)
    report={
        "scope":"SignalLock v0.3 second-order adversarial regression audit; intentionally hostile, not a production accuracy estimate",
        "created_at_utc":datetime.now(timezone.utc).isoformat(),
        "unsafe_text":{"total":len(unsafe),"pass":sum(x["decision"]=="PASS" for x in unsafe),"review":sum(x["decision"]=="REVIEW" for x in unsafe),"block":sum(x["decision"]=="BLOCK" for x in unsafe),"cases":unsafe},
        "safe_text":{"total":len(safe),"pass":sum(x["decision"]=="PASS" for x in safe),"review":sum(x["decision"]=="REVIEW" for x in safe),"block":sum(x["decision"]=="BLOCK" for x in safe),"cases":safe},
        "cap_material_changes":{"total":len(caps),"unsafe_passes":sum(x.get("decision")=="PASS" for x in caps),"cases":caps},
        "authority_tamper":authority_tamper(),
        "model_semantic_lie":asyncio.run(model_semantic_lie()),
        "hazard_description_change":{"decision":hazard.decision.value,"safe":hazard.decision.value!="PASS"},
        "source_mutually_exclusive_actions":{"decision":conflict["decision"],"safe":conflict["decision"]!="PASS"},
        "v7_holdout_gaming":holdout_gaming(),
        "v7_preflight":{"exit_code":preflight.returncode,"fail_closed":preflight.returncode!=0},
    }
    report["passed"]=(report["unsafe_text"]["pass"]==0 and report["safe_text"]["pass"]==len(SAFE) and report["cap_material_changes"]["unsafe_passes"]==0 and report["authority_tamper"]["safe"] and report["model_semantic_lie"]["safe"] and report["hazard_description_change"]["safe"] and report["source_mutually_exclusive_actions"]["safe"] and report["v7_holdout_gaming"]["strict_sealer_refused"] and not report["v7_holdout_gaming"]["numeric_only_gate"]["passed"] and report["v7_preflight"]["fail_closed"])
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"passed":report["passed"],"unsafe_text":report["unsafe_text"],"safe_text":report["safe_text"],"cap_unsafe_passes":report["cap_material_changes"]["unsafe_passes"],"authority_tamper":report["authority_tamper"],"model_semantic_lie":report["model_semantic_lie"],"v7_holdout_gaming":report["v7_holdout_gaming"],"preflight_exit":preflight.returncode},ensure_ascii=False,indent=2))
    if not report["passed"]: raise SystemExit(2)

if __name__ == "__main__": main()
