from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api.main import app
from signallock.benchmark.metrics import BenchmarkCaseResult, compute_metrics
from signallock.benchmark.runner import run_demo_benchmark
from signallock.cap.mapper import cap_info_seed_contract
from signallock.cap.parser import parse_cap_xml
from signallock.contracts.extractor import HeuristicExtractor
from signallock.contracts.schema import (
    Action,
    ActionType,
    Certainty,
    Hazard,
    Quantity,
    QuantityRelation,
    SafetyContract,
    Severity,
    Urgency,
)
from signallock.providers.openai_http import OpenAIResponsesProvider, ProviderError
from signallock.transforms.demo import DemoTransformer
from signallock.verification.engine import VerificationEngine

OUT = ROOT / "data" / "results" / "postrepair_audit.json"
E = HeuristicExtractor()
V = VerificationEngine()
BASE = (
    "Residents in the eastern river district must shelter indoors until 6 PM. "
    "Do not enter the eastern underpass. Avoid roads with more than 30 cm of water, except emergency personnel."
)


def verify_text(source: str, candidate: str):
    return V.verify(E.extract(source), E.extract(candidate))


def decision_rows(cases):
    rows = []
    for name, source, candidate in cases:
        result = verify_text(source, candidate)
        rows.append({
            "name": name,
            "decision": result.decision.value,
            "critical_failures": result.critical_failures,
            "warnings": result.warnings,
        })
    return rows


UNSAFE_TEXT = [
    ("add_conflicting_evacuate", BASE, BASE + " Evacuate immediately."),
    ("add_contradictory_prohibition", BASE, BASE + " Do not shelter indoors."),
    ("add_conflicting_quantity", BASE, BASE + " Avoid water deeper than 3 cm."),
    ("add_new_area", BASE, BASE + " Residents in the western river district must also shelter indoors."),
    ("add_new_audience", BASE, BASE + " Visitors should follow this alert too."),
    ("flip_exception_scope", BASE, BASE.replace("except emergency personnel", "except non-emergency personnel")),
    ("flip_audience_scope", BASE, BASE.replace("Residents", "Non-residents", 1)),
    ("higher_to_lower_ground", "Move to higher ground immediately.", "Move to lower ground immediately."),
    ("boil_to_drink", "Boil tap water for 3 minutes before drinking.", "Drink tap water without boiling."),
    ("gas_off_to_on", "Turn off the gas supply.", "Turn on the gas supply."),
    ("second_floor_to_basement", "Take shelter on the second floor.", "Take shelter in the basement."),
    ("no_evac_to_evac", "No evacuation is currently required.", "Evacuation is required immediately."),
    ("windows", "Stay away from windows.", "Stand near windows."),
]

SAFE_TEXT = [
    ("builtin_simplify", BASE, DemoTransformer().transform(BASE, mode="simplify")),
    ("east_direction_synonym", BASE, BASE.replace("eastern river district", "east river district")),
    ("keep_out_synonym", BASE, BASE.replace("Do not enter the eastern underpass", "Keep out of the eastern underpass")),
    ("people_audience", BASE, BASE.replace("Residents", "People living in the area", 1)),
    ("remain_inside", BASE, BASE.replace("shelter indoors", "remain inside")),
    ("emergency_staff", BASE, BASE.replace("except emergency personnel", "except emergency staff")),
    ("unit_conversion", BASE, BASE.replace("30 cm", "0.3 m")),
    ("time_24h", BASE, BASE.replace("6 PM", "18:00")),
    ("never_enter", BASE, BASE.replace("Do not enter", "Never enter")),
    ("all_residents", BASE, BASE.replace("Residents", "All residents", 1)),
]


def run_contract_semantics():
    cases = [
        (
            "antonym_substring",
            SafetyContract(required_actions=[Action(type=ActionType.OTHER, verb="disconnect", object="gas supply")]),
            SafetyContract(required_actions=[Action(type=ActionType.OTHER, verb="connect", object="gas supply")]),
        ),
        (
            "condition_removed",
            SafetyContract(required_actions=[Action(type=ActionType.EVACUATE, verb="evacuate", condition="only if officials order")]),
            SafetyContract(required_actions=[Action(type=ActionType.EVACUATE, verb="evacuate")]),
        ),
        (
            "destination_added",
            SafetyContract(required_actions=[Action(type=ActionType.EVACUATE, verb="evacuate")]),
            SafetyContract(required_actions=[Action(type=ActionType.EVACUATE, verb="evacuate", destination="unsafe tunnel")]),
        ),
        (
            "deadline_added",
            SafetyContract(required_actions=[Action(type=ActionType.EVACUATE, verb="evacuate")]),
            SafetyContract(required_actions=[Action(type=ActionType.EVACUATE, verb="evacuate", deadline="8 PM")]),
        ),
        ("urgency_changed", SafetyContract(urgency=Urgency.IMMEDIATE), SafetyContract(urgency=Urgency.FUTURE)),
        ("severity_changed", SafetyContract(severity=Severity.EXTREME), SafetyContract(severity=Severity.MINOR)),
        ("certainty_changed", SafetyContract(certainty=Certainty.OBSERVED), SafetyContract(certainty=Certainty.UNLIKELY)),
        ("hazard_changed", SafetyContract(hazard=Hazard(type="flood")), SafetyContract(hazard=Hazard(type="wildfire"))),
        (
            "expiry_changed",
            SafetyContract(
                effective_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
                expires_at=datetime(2026, 9, 10, 18, tzinfo=timezone.utc),
            ),
            SafetyContract(
                effective_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
                expires_at=datetime(2026, 9, 10, 20, tzinfo=timezone.utc),
            ),
        ),
        (
            "quantity_meaning_changed",
            SafetyContract(quantities=[Quantity(value=30, unit="cm", relation=QuantityRelation.GREATER_THAN, meaning="water depth")]),
            SafetyContract(quantities=[Quantity(value=30, unit="cm", relation=QuantityRelation.GREATER_THAN, meaning="safe clearance")]),
        ),
        (
            "quantity_relation_changed",
            SafetyContract(quantities=[Quantity(value=30, unit="cm", relation=QuantityRelation.GREATER_THAN, meaning="water depth")]),
            SafetyContract(quantities=[Quantity(value=30, unit="cm", relation=QuantityRelation.LESS_THAN, meaning="water depth")]),
        ),
        (
            "extra_required_action",
            SafetyContract(required_actions=[Action(type=ActionType.SHELTER, verb="shelter", destination="indoors")]),
            SafetyContract(required_actions=[
                Action(type=ActionType.SHELTER, verb="shelter", destination="indoors"),
                Action(type=ActionType.EVACUATE, verb="evacuate"),
            ]),
        ),
        (
            "extra_quantity",
            SafetyContract(quantities=[Quantity(value=30, unit="cm", meaning="water depth")]),
            SafetyContract(quantities=[
                Quantity(value=30, unit="cm", meaning="water depth"),
                Quantity(value=3, unit="cm", meaning="water depth"),
            ]),
        ),
        (
            "extra_area",
            SafetyContract(affected_areas=["East Zone"]),
            SafetyContract(affected_areas=["East Zone", "West Zone"]),
        ),
        (
            "typed_surface_verb_conflict",
            SafetyContract(required_actions=[Action(type=ActionType.SHELTER, verb="shelter", destination="indoors")]),
            SafetyContract(required_actions=[Action(type=ActionType.SHELTER, verb="evacuate", destination="indoors")]),
        ),
    ]
    out = []
    for name, source, candidate in cases:
        result = V.verify(source, candidate)
        out.append({"name": name, "decision": result.decision.value})
    return out


def extraction_edges():
    checks = {}
    c = E.extract("Avoid roads with more than 1,500 meters of flooding.")
    checks["thousands_1500m"] = [(q.value, q.unit, q.relation.value) for q in c.quantities]
    c = E.extract("Avoid roads with more than 2,000 mm of water.")
    checks["thousands_2000mm"] = [(q.value, q.unit, q.relation.value) for q in c.quantities]
    c = E.extract("Avoid travel below -5 C.")
    checks["negative_temperature"] = [(q.value, q.unit, q.relation.value) for q in c.quantities]
    c = E.extract("Wind speed may reach 60 km/h.")
    checks["compound_unit"] = [(q.value, q.unit, q.meaning) for q in c.quantities]
    c = E.extract("Water level may reach 30%.")
    checks["percentage"] = [(q.value, q.unit) for q in c.quantities]
    c = E.extract("Shelter indoors. Roads reopen by 6 PM.")
    checks["sentence_local_deadline"] = [a.deadline for a in c.required_actions]
    c = E.extract("Shelter indoors until noon.")
    checks["noon_deadline"] = [a.deadline for a in c.required_actions]
    return checks


class FakeProvider(OpenAIResponsesProvider):
    mode = "bad_provenance"

    async def _request(self, payload):
        if self.mode == "bad_provenance":
            contract = {
                "schema_version": "1.0",
                "language": "en",
                "hazard": None,
                "audience": [],
                "affected_areas": [],
                "required_actions": [{
                    "type": "EVACUATE", "verb": "evacuate", "object": None,
                    "destination": None, "condition": None, "deadline": None,
                    "negated": False,
                    "evidence": {"quote": "THIS DOES NOT EXIST", "start_char": 0, "end_char": 19},
                }],
                "prohibited_actions": [],
                "urgency": "Unknown", "severity": "Unknown", "certainty": "Unknown",
                "effective_at": None, "expires_at": None, "quantities": [], "exceptions": [],
                "unresolved_operational_text": [], "source_id": None,
            }
            return {"output": [{"content": [{"type": "output_text", "text": json.dumps(contract)}]}]}
        return {"output": [{"content": [{"type": "output_text", "text": "X" * 500}]}]}


async def provider_checks():
    p = FakeProvider(api_key="test")
    bad_provenance_rejected = False
    try:
        await p.extract_contract("Shelter indoors.", language="en")
    except ProviderError:
        bad_provenance_rejected = True

    p.mode = "long_sms"
    oversize_sms_rejected = False
    try:
        await p.transform("source", mode="sms", max_chars=80)
    except ProviderError:
        oversize_sms_rejected = True
    return {
        "bad_provenance_rejected": bad_provenance_rejected,
        "oversize_sms_rejected": oversize_sms_rejected,
    }


def cap_checks():
    fixture = (ROOT / "tests" / "fixtures" / "sample_cap.xml").read_text(encoding="utf-8")
    alert = parse_cap_xml(fixture)
    en = cap_info_seed_contract(alert, alert.infos[0])

    invalid_enum_rejected = False
    try:
        parse_cap_xml(
            "<alert><identifier>Z</identifier><sender>x@y</sender><sent>2026-09-10T12:00:00Z</sent>"
            "<status>BANANA</status><msgType>Alert</msgType><scope>Public</scope></alert>"
        )
    except ValueError:
        invalid_enum_rejected = True

    missing_info_core_rejected = False
    try:
        parse_cap_xml(
            "<alert><identifier>Z</identifier><sender>x@y</sender><sent>2026-09-10T12:00:00Z</sent>"
            "<status>Actual</status><msgType>Alert</msgType><scope>Public</scope>"
            "<info><event>Flood</event></info></alert>"
        )
    except ValueError:
        missing_info_core_rejected = True

    nonenglish = parse_cap_xml(
        "<alert><identifier>H</identifier><sender>x@y</sender><sent>2026-09-10T12:00:00Z</sent>"
        "<status>Actual</status><msgType>Alert</msgType><scope>Public</scope>"
        "<info><language>hi-IN</language><category>Met</category><event>Flood</event>"
        "<urgency>Immediate</urgency><severity>Severe</severity><certainty>Likely</certainty>"
        "<instruction>तुरंत ऊंची जगह पर जाएं।</instruction></info></alert>"
    )
    hi = cap_info_seed_contract(nonenglish, nonenglish.infos[0])
    return {
        "english_instruction_required_actions": len(en.required_actions),
        "english_instruction_prohibited_actions": len(en.prohibited_actions),
        "invalid_enum_rejected": invalid_enum_rejected,
        "missing_info_core_rejected": missing_info_core_rejected,
        "nonenglish_instruction_unresolved": bool(hi.unresolved_operational_text),
    }


def schema_checks():
    invalid_prohibition_rejected = False
    try:
        SafetyContract(prohibited_actions=[Action(type=ActionType.AVOID, verb="enter", object="tunnel", negated=False)])
    except ValidationError:
        invalid_prohibition_rejected = True
    return {"invalid_prohibition_rejected": invalid_prohibition_rejected}


def api_checks():
    client = TestClient(app)
    health = client.get("/health").json()
    unsafe = client.post("/api/verify", json={
        "source_text": "Do not enter the eastern underpass. Shelter indoors until 6 PM.",
        "candidate_text": "Enter the eastern underpass. Shelter indoors until 6 PM.",
        "source_language": "en", "candidate_language": "en", "provider": "heuristic",
    })
    safe = client.post("/api/verify", json={
        "source_text": "Residents must shelter indoors until 6 PM.",
        "candidate_text": "People living in the area must stay indoors until 18:00.",
        "source_language": "en", "candidate_language": "en", "provider": "heuristic",
    })
    return {
        "health_version": health["version"],
        "unsafe_status": unsafe.status_code,
        "unsafe_decision": unsafe.json().get("decision"),
        "safe_status": safe.status_code,
        "safe_decision": safe.json().get("decision"),
    }


def main():
    unsafe = decision_rows(UNSAFE_TEXT)
    safe = decision_rows(SAFE_TEXT)
    contracts = run_contract_semantics()

    empty = V.verify(SafetyContract(), SafetyContract())
    contradictory_text = "Shelter indoors. Do not shelter indoors."
    contradictory_contract = E.extract(contradictory_text)
    contradiction = V.verify(contradictory_contract, contradictory_contract)

    all_review_rows = [BenchmarkCaseResult(f"u{i}", "X", True, "REVIEW", True) for i in range(20)]
    all_review_rows += [BenchmarkCaseResult(f"c{i}", "CLEAN", False, "REVIEW", True) for i in range(20)]
    degenerate = compute_metrics(all_review_rows).to_dict()

    benchmark = run_demo_benchmark()["metrics"]
    report = {
        "scope": "post-repair targeted regression audit; controlled development evidence, not production safety",
        "unsafe_text": {
            "total": len(unsafe),
            "pass": sum(r["decision"] == "PASS" for r in unsafe),
            "review": sum(r["decision"] == "REVIEW" for r in unsafe),
            "block": sum(r["decision"] == "BLOCK" for r in unsafe),
            "cases": unsafe,
        },
        "safe_text": {
            "total": len(safe),
            "pass": sum(r["decision"] == "PASS" for r in safe),
            "review": sum(r["decision"] == "REVIEW" for r in safe),
            "block": sum(r["decision"] == "BLOCK" for r in safe),
            "cases": safe,
        },
        "contract_semantics": {
            "total": len(contracts),
            "pass": sum(r["decision"] == "PASS" for r in contracts),
            "cases": contracts,
        },
        "empty_contract_decision": empty.decision.value,
        "source_internal_contradiction_decision": contradiction.decision.value,
        "metric_degeneracy": {
            "all_review_clean_pass_rate": degenerate["clean_pass_rate"],
            "all_review_unsafe_block_rate": degenerate["unsafe_block_rate"],
            "all_review_useful_coverage": degenerate["useful_coverage"],
        },
        "extraction_edges": extraction_edges(),
        "provider": asyncio.run(provider_checks()),
        "cap": cap_checks(),
        "schema": schema_checks(),
        "api": api_checks(),
        "benchmark": benchmark,
    }

    assertions = {
        "unsafe_text_no_pass": report["unsafe_text"]["pass"] == 0,
        "safe_text_all_pass": report["safe_text"]["pass"] == len(SAFE_TEXT),
        "contract_corruptions_no_pass": report["contract_semantics"]["pass"] == 0,
        "empty_contract_reviews": report["empty_contract_decision"] == "REVIEW",
        "source_contradiction_reviews": report["source_internal_contradiction_decision"] == "REVIEW",
        "all_review_cannot_meet_usefulness_gate": (
            report["metric_degeneracy"]["all_review_clean_pass_rate"] == 0
            and report["metric_degeneracy"]["all_review_unsafe_block_rate"] == 0
            and report["metric_degeneracy"]["all_review_useful_coverage"] == 0
        ),
        "provider_fail_closed": all(report["provider"].values()),
        "cap_fail_closed": (
            report["cap"]["invalid_enum_rejected"]
            and report["cap"]["missing_info_core_rejected"]
            and report["cap"]["nonenglish_instruction_unresolved"]
        ),
        "schema_polarity_hardened": report["schema"]["invalid_prohibition_rejected"],
        "api_unsafe_blocks": report["api"]["unsafe_decision"] == "BLOCK",
        "api_safe_passes": report["api"]["safe_decision"] == "PASS",
        "benchmark_gate": (
            benchmark["critical_unsafe_pass_rate"] <= 0.05
            and benchmark["unsafe_catch_recall"] >= 0.98
            and benchmark["unsafe_block_rate"] >= 0.90
            and benchmark["clean_pass_rate"] >= 0.80
            and benchmark["clean_review_rate"] <= 0.15
            and benchmark["clean_block_rate"] <= 0.10
        ),
    }
    report["assertions"] = assertions
    report["passed"] = all(assertions.values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({
        "passed": report["passed"],
        "assertions": assertions,
        "unsafe_text": {k: report["unsafe_text"][k] for k in ("total", "pass", "review", "block")},
        "safe_text": {k: report["safe_text"][k] for k in ("total", "pass", "review", "block")},
        "contract_semantics": {k: report["contract_semantics"][k] for k in ("total", "pass")},
        "benchmark": {
            "total": benchmark["total"],
            "critical_unsafe_pass_rate": benchmark["critical_unsafe_pass_rate"],
            "unsafe_block_rate": benchmark["unsafe_block_rate"],
            "clean_pass_rate": benchmark["clean_pass_rate"],
        },
        "output": str(OUT),
    }, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
