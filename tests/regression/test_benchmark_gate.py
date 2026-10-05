from signallock.benchmark.runner import run_demo_benchmark


def test_demo_benchmark_safety_and_usefulness_gate():
    report = run_demo_benchmark()
    metrics = report["metrics"]
    assert metrics["critical_unsafe_pass_rate"] <= 0.05
    assert metrics["unsafe_catch_recall"] >= 0.98
    assert metrics["unsafe_block_rate"] >= 0.90
    assert metrics["clean_pass_rate"] >= 0.80
    assert metrics["clean_review_rate"] <= 0.15
    assert metrics["clean_block_rate"] <= 0.10
    assert metrics["selective_unsafe_pass_rate"] <= 0.05
