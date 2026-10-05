from aquasignal.evaluation.runner import run_cases


def test_dev_benchmark_has_zero_unsafe_pass_and_useful_clean_pass_rate():
    result = run_cases()
    assert result["unsafe_pass"] == 0
    assert result["clean_pass_rate"] >= 0.8
    assert result["clean_block_rate"] <= 0.05


def test_release_qualifier_requires_every_declared_critical_family_to_exist_and_block():
    from aquasignal.evaluation.evidence import _qualify
    metrics = {
        "unsafe_pass": 0,
        "unsafe_total": 1,
        "clean_total": 1,
        "clean_pass_rate": 1.0,
        "clean_block_rate": 0.0,
        "expected_failures": [],
        "per_family": {"time_reversal": {"BLOCK": 1}},
    }
    manifest = {
        "min_clean_pass_rate": 0.8,
        "max_clean_block_rate": 0.05,
        "critical_block_families": ["time_reversal", "audience_omission"],
    }
    qualified, errors = _qualify(metrics, manifest)
    assert not qualified
    assert any("audience_omission" in error and "absent" in error for error in errors)


def test_release_manifest_counts_must_match_recomputed_metrics():
    from aquasignal.evaluation.evidence import _validate_manifest_counts
    metrics = {"total": 10, "unsafe_total": 6, "clean_total": 4}
    assert _validate_manifest_counts(metrics, {"case_count": 10, "unsafe_count": 6, "clean_count": 4}) == []
    errors = _validate_manifest_counts(metrics, {"case_count": 999, "unsafe_count": 0, "clean_count": 4})
    assert len(errors) == 2
