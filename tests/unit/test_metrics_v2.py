from signallock.benchmark.metrics import BenchmarkCaseResult, compute_metrics


def test_all_review_cannot_look_perfect():
    rows = [BenchmarkCaseResult(f"u{i}", "X", True, "REVIEW", True) for i in range(10)]
    rows += [BenchmarkCaseResult(f"c{i}", "CLEAN", False, "REVIEW", True) for i in range(10)]
    m = compute_metrics(rows)
    assert m.clean_pass_rate == 0.0
    assert m.clean_review_rate == 1.0
    assert m.unsafe_block_rate == 0.0
    assert m.useful_coverage == 0.0


def test_metrics_separate_block_review_and_pass():
    rows = [
        BenchmarkCaseResult("u1", "X", True, "BLOCK", True),
        BenchmarkCaseResult("u2", "X", True, "REVIEW", True),
        BenchmarkCaseResult("u3", "X", True, "PASS", False),
        BenchmarkCaseResult("c1", "CLEAN", False, "PASS", True),
        BenchmarkCaseResult("c2", "CLEAN", False, "REVIEW", True),
        BenchmarkCaseResult("c3", "CLEAN", False, "BLOCK", False),
    ]
    m = compute_metrics(rows)
    assert m.unsafe_block_rate == 1 / 3
    assert m.unsafe_review_rate == 1 / 3
    assert m.critical_unsafe_pass_rate == 1 / 3
    assert m.clean_pass_rate == 1 / 3
    assert m.clean_review_rate == 1 / 3
    assert m.clean_block_rate == 1 / 3
