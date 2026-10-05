from signallock.contracts.normalization import normalize_text, normalize_time_string, quantities_equivalent


def test_text_normalization():
    assert normalize_text("  Eastern—UNDERPASS!! ") == "eastern underpass"


def test_equivalent_units():
    assert quantities_equivalent(30, "cm", 0.3, "m")
    assert quantities_equivalent(300, "mm", 30, "cm")


def test_non_equivalent_units():
    assert not quantities_equivalent(30, "cm", 3, "cm")


def test_time_normalization():
    assert normalize_time_string("6 PM") == "18:00"
    assert normalize_time_string("18:00") == "18:00"
