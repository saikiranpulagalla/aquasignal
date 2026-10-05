from __future__ import annotations

from collections import Counter, defaultdict

from aquasignal.domain.freshwater import FreshwaterExtractor, assess_source_readiness
from aquasignal.integrity.verifier import AquaVerificationEngine
from aquasignal.evaluation.cases import DEV_CASES, AquaCase


def run_cases(cases: list[AquaCase] | None = None) -> dict:
    cases = list(cases or DEV_CASES)
    extractor = FreshwaterExtractor()
    verifier = AquaVerificationEngine()
    rows = []
    counts = Counter()
    families = defaultdict(Counter)
    expectation_failures: list[str] = []
    for case in cases:
        source = extractor.extract(case.source, source_id=case.case_id + ":source")
        candidate = extractor.extract(case.candidate, source_id=case.case_id + ":candidate")
        readiness = assess_source_readiness(source)
        if not readiness.ready:
            decision = "SOURCE_REVIEW"
        else:
            decision = verifier.verify(source, candidate).decision.value
        group = "clean" if case.safe_equivalent else "unsafe"
        counts[f"{group}_{decision.casefold()}"] += 1
        families[case.family][decision] += 1
        expected_met = case.expected_decision is None or case.expected_decision == decision
        if not expected_met:
            expectation_failures.append(case.case_id)
        rows.append({
            "case_id": case.case_id,
            "family": case.family,
            "safe_equivalent": case.safe_equivalent,
            "decision": decision,
            "expected_decision": case.expected_decision,
            "expected_met": expected_met,
            "source_ready": readiness.ready,
        })
    unsafe_total = sum(v for k, v in counts.items() if k.startswith("unsafe_"))
    clean_total = sum(v for k, v in counts.items() if k.startswith("clean_"))

    def rate(key: str, denom: int) -> float:
        return counts[key] / denom if denom else 0.0

    return {
        "profile": FreshwaterExtractor.profile.profile_id,
        "total": len(cases),
        "unsafe_total": unsafe_total,
        "clean_total": clean_total,
        "unsafe_pass": counts["unsafe_pass"],
        "unsafe_block": counts["unsafe_block"],
        "unsafe_review": counts["unsafe_review"],
        "unsafe_source_review": counts["unsafe_source_review"],
        "clean_pass": counts["clean_pass"],
        "clean_block": counts["clean_block"],
        "clean_review": counts["clean_review"],
        "clean_source_review": counts["clean_source_review"],
        "unsafe_pass_rate": rate("unsafe_pass", unsafe_total),
        "unsafe_block_rate": rate("unsafe_block", unsafe_total),
        "clean_pass_rate": rate("clean_pass", clean_total),
        "clean_block_rate": rate("clean_block", clean_total),
        "expected_failures": expectation_failures,
        "expected_pass_rate": (len(cases) - len(expectation_failures)) / len(cases) if cases else 0.0,
        "per_family": {k: dict(v) for k, v in sorted(families.items())},
        "cases": rows,
    }
