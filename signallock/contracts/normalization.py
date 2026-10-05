from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime


_WS = re.compile(r"\s+")


_TEXT_ALIASES = {
    "all residents": "residents",
    "people living": "residents",
    "people living in the area": "residents",
    "residents": "residents",
    "निवासी": "residents",
    "నివాసితులు": "residents",
    "emergency staff": "emergency personnel",
    "emergency responders": "emergency personnel",
    "emergency personnel": "emergency personnel",
    "आपातकालीन कर्मचारी": "emergency personnel",
    "అత్యవసర సిబ్బంది": "emergency personnel",
    "inside": "indoors",
    "within buildings": "indoors",
    "home indoors": "indoors",
    "घर के अंदर": "indoors",
    "లోపల": "indoors",
    "ఇంటి లోపల": "indoors",
}

_DIRECTION_ALIASES = {
    "eastern": "east",
    "western": "west",
    "northern": "north",
    "southern": "south",
    "पूर्वी": "east",
    "पश्चिमी": "west",
    "उत्तरी": "north",
    "दक्षिणी": "south",
    "తూర్పు": "east",
    "పడమర": "west",
    "ఉత్తర": "north",
    "దక్షిణ": "south",
    "नदी": "river",
    "जिला": "district",
    "నది": "river",
    "జిల్లా": "district",
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    chars: list[str] = []
    for ch in value:
        category = unicodedata.category(ch)
        if ch.isspace() or category[0] in {"L", "N", "M"} or ch in {"/", "%", "+", "-"}:
            chars.append(ch)
        else:
            chars.append(" ")
    return _WS.sub(" ", "".join(chars)).strip()


def canonical_text(value: str | None) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    # Whole-phrase aliases are safe; never use substring containment for critical semantics.
    if text in _TEXT_ALIASES:
        return _TEXT_ALIASES[text]
    tokens = [_DIRECTION_ALIASES.get(tok, tok) for tok in text.split()]
    text = " ".join(tok for tok in tokens if tok not in {"the", "a", "an"})
    return _TEXT_ALIASES.get(text, text)


def normalize_token_set(value: str | None) -> set[str]:
    return set(canonical_text(value).split())


def normalize_unit(unit: str) -> str:
    value = normalize_text(unit)
    aliases = {
        "centimeter": "cm", "centimeters": "cm", "centimetre": "cm", "centimetres": "cm",
        "meter": "m", "meters": "m", "metre": "m", "metres": "m",
        "millimeter": "mm", "millimeters": "mm", "millimetre": "mm", "millimetres": "mm",
        "kilometer": "km", "kilometers": "km", "kilometre": "km", "kilometres": "km",
        "kilometre per hour": "km/h", "kilometers per hour": "km/h", "kilometer per hour": "km/h",
        "kilometres per hour": "km/h", "km h": "km/h", "km/h": "km/h",
        "degrees celsius": "c", "degree celsius": "c", "celsius": "c", "°c": "c", "c": "c",
        "hours": "h", "hour": "h", "hrs": "h", "hr": "h", "h": "h",
        "minutes": "min", "minute": "min", "mins": "min", "min": "min",
        "seconds": "s", "second": "s", "secs": "s", "sec": "s", "s": "s",
        "%": "%", "percent": "%", "percentage": "%",
    }
    return aliases.get(value, value)


def quantities_equivalent(
    a_value: float,
    a_unit: str,
    b_value: float,
    b_unit: str,
    *,
    rel_tol: float = 1e-9,
    abs_tol: float = 0.0,
) -> bool:
    """Compare normalized physical quantities without an unsafe fixed absolute window.

    The former 1e-6 absolute tolerance could make a 90% change at very small
    magnitudes appear equivalent (for example 1e-6 s vs 1e-7 s).  A tight
    relative tolerance with zero absolute tolerance keeps ordinary unit-conversion
    floating-point noise stable without erasing small safety-critical values.
    Non-finite values are never considered equivalent.
    """
    if not (math.isfinite(a_value) and math.isfinite(b_value)):
        return False

    au = normalize_unit(a_unit)
    bu = normalize_unit(b_unit)

    def close(left: float, right: float) -> bool:
        return math.isclose(left, right, rel_tol=rel_tol, abs_tol=abs_tol)

    if au == bu:
        return close(a_value, b_value)

    conversions = {
        ("cm", "m"): lambda x: x / 100,
        ("m", "cm"): lambda x: x * 100,
        ("mm", "cm"): lambda x: x / 10,
        ("cm", "mm"): lambda x: x * 10,
        ("mm", "m"): lambda x: x / 1000,
        ("m", "mm"): lambda x: x * 1000,
        ("km", "m"): lambda x: x * 1000,
        ("m", "km"): lambda x: x / 1000,
        ("h", "min"): lambda x: x * 60,
        ("min", "h"): lambda x: x / 60,
        ("min", "s"): lambda x: x * 60,
        ("s", "min"): lambda x: x / 60,
        ("h", "s"): lambda x: x * 3600,
        ("s", "h"): lambda x: x / 3600,
    }
    fn = conversions.get((au, bu))
    return fn is not None and close(fn(a_value), b_value)


def normalize_time_string(value: str | None) -> str:
    if not value:
        return ""
    raw = unicodedata.normalize("NFKC", value).casefold().strip().replace(".", "")
    raw = _WS.sub(" ", raw)
    # The extractor accepts both "6 PM" and "6pm"; normalize the attached
    # meridiem form before datetime parsing so accepted syntax has identical semantics.
    raw = re.sub(r"(?<=\d)(am|pm)$", r" \1", raw)
    if raw == "noon":
        return "12:00"
    if raw == "midnight":
        return "00:00"
    patterns = ["%I:%M %p", "%I %p", "%H:%M", "%H%M"]
    for fmt in patterns:
        try:
            return datetime.strptime(raw, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return normalize_text(value)
