from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, asdict


@dataclass(slots=True)
class BenchmarkCaseResult:
    case_id: str
    fault: str
    unsafe: bool
    decision: str
    caught: bool


@dataclass(slots=True)
class BenchmarkMetrics:
    total: int
    unsafe_total: int
    clean_total: int
    unsafe_passes: int
    unsafe_blocks: int
    unsafe_reviews: int
    clean_passes: int
    clean_blocks: int
    clean_reviews: int
    critical_unsafe_pass_rate: float
    unsafe_catch_recall: float
    unsafe_block_rate: float
    unsafe_review_rate: float
    clean_pass_rate: float
    clean_review_rate: float
    clean_block_rate: float
    useful_coverage: float
    selective_unsafe_pass_rate: float
    decision_counts: dict[str, int]
    per_fault: dict[str, dict[str, float | int]]

    def to_dict(self) -> dict:
        return asdict(self)


def _rate(n: int, d: int) -> float:
    return (n / d) if d else 0.0


def compute_metrics(results: list[BenchmarkCaseResult]) -> BenchmarkMetrics:
    unsafe = [r for r in results if r.unsafe]
    clean = [r for r in results if not r.unsafe]

    unsafe_passes = sum(r.decision == "PASS" for r in unsafe)
    unsafe_blocks = sum(r.decision == "BLOCK" for r in unsafe)
    unsafe_reviews = sum(r.decision == "REVIEW" for r in unsafe)
    clean_passes = sum(r.decision == "PASS" for r in clean)
    clean_blocks = sum(r.decision == "BLOCK" for r in clean)
    clean_reviews = sum(r.decision == "REVIEW" for r in clean)
    caught = unsafe_blocks + unsafe_reviews

    groups: dict[str, list[BenchmarkCaseResult]] = defaultdict(list)
    for r in results:
        groups[r.fault].append(r)

    per_fault: dict[str, dict[str, float | int]] = {}
    for fault, rows in groups.items():
        unsafe_rows = [r for r in rows if r.unsafe]
        clean_rows = [r for r in rows if not r.unsafe]
        denom = len(unsafe_rows) or len(clean_rows)
        block = sum(r.decision == "BLOCK" for r in rows)
        review = sum(r.decision == "REVIEW" for r in rows)
        passed = sum(r.decision == "PASS" for r in rows)
        per_fault[fault] = {
            "total": len(rows),
            "caught": sum(r.caught for r in rows),
            "catch_rate": _rate(sum(r.caught for r in rows), denom),
            "pass_rate": _rate(passed, len(rows)),
            "review_rate": _rate(review, len(rows)),
            "block_rate": _rate(block, len(rows)),
        }

    # Useful coverage means the fraction of clean transformations the verifier can actually approve.
    useful_coverage = _rate(clean_passes, len(clean))
    # Selective risk measures danger among cases the system chose to approve.
    total_passes = unsafe_passes + clean_passes
    selective_unsafe_pass_rate = _rate(unsafe_passes, total_passes)

    return BenchmarkMetrics(
        total=len(results),
        unsafe_total=len(unsafe),
        clean_total=len(clean),
        unsafe_passes=unsafe_passes,
        unsafe_blocks=unsafe_blocks,
        unsafe_reviews=unsafe_reviews,
        clean_passes=clean_passes,
        clean_blocks=clean_blocks,
        clean_reviews=clean_reviews,
        critical_unsafe_pass_rate=_rate(unsafe_passes, len(unsafe)),
        unsafe_catch_recall=_rate(caught, len(unsafe)),
        unsafe_block_rate=_rate(unsafe_blocks, len(unsafe)),
        unsafe_review_rate=_rate(unsafe_reviews, len(unsafe)),
        clean_pass_rate=_rate(clean_passes, len(clean)),
        clean_review_rate=_rate(clean_reviews, len(clean)),
        clean_block_rate=_rate(clean_blocks, len(clean)),
        useful_coverage=useful_coverage,
        selective_unsafe_pass_rate=selective_unsafe_pass_rate,
        decision_counts=dict(Counter(r.decision for r in results)),
        per_fault=per_fault,
    )
