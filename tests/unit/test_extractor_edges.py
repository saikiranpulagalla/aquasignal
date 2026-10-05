import pytest

from signallock.contracts.extractor import HeuristicExtractor
from signallock.contracts.normalization import normalize_time_string

E = HeuristicExtractor()


@pytest.mark.parametrize(
    "text,value,unit",
    [
        ("Avoid roads with more than 1,500 meters of flooding.", 1500, "meters"),
        ("Avoid roads with more than 2,000 mm of water.", 2000, "mm"),
        ("Avoid travel below -5 C.", -5, "C"),
        ("Wind speed may reach 60 km/h.", 60, "km/h"),
        ("Water level may reach 30%.", 30, "%"),
    ],
)
def test_numeric_formats(text, value, unit):
    q = E.extract(text).quantities
    assert q
    assert q[0].value == value
    assert q[0].unit.casefold() == unit.casefold()


def test_time_does_not_cross_sentence_boundary():
    c = E.extract("Shelter indoors. Roads reopen by 6 PM.")
    assert c.required_actions
    assert c.required_actions[0].deadline is None


def test_noon_time_supported():
    c = E.extract("Shelter indoors until noon.")
    assert normalize_time_string(c.required_actions[0].deadline) == "12:00"
