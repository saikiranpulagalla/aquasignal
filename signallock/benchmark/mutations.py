from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class FaultClass(StrEnum):
    ACTION_REMOVED = "F01_ACTION_REMOVED"
    ACTION_CHANGED = "F02_ACTION_CHANGED"
    NEGATION_FLIPPED = "F03_NEGATION_FLIPPED"
    LOCATION_CHANGED = "F04_LOCATION_CHANGED"
    QUANTITY_CHANGED = "F05_QUANTITY_CHANGED"
    TIME_CHANGED = "F06_TIME_CHANGED"
    AUDIENCE_CHANGED = "F07_AUDIENCE_CHANGED"
    EXCEPTION_REMOVED = "F08_EXCEPTION_REMOVED"
    CLEAN = "CLEAN"


@dataclass(frozen=True, slots=True)
class Mutation:
    fault: FaultClass
    text: str
    unsafe: bool
    note: str


def inject_negation_flip(text: str) -> Mutation:
    changed, n = re.subn(r"\b(?:do\s+not|don't|never|must\s+not)\s+", "", text, count=1, flags=re.I)
    if not n:
        changed, n = re.subn(r"\b(evacuate|enter|use|drive|cross|leave)\b", r"do not \1", text, count=1, flags=re.I)
    return Mutation(FaultClass.NEGATION_FLIPPED, changed, True, "Protective-action polarity reversed")


def inject_quantity_change(text: str) -> Mutation:
    def repl(match: re.Match[str]) -> str:
        value = float(match.group(1))
        new = value / 10 if value >= 10 else value * 10
        new_text = str(int(new)) if float(new).is_integer() else str(new)
        return f"{new_text} {match.group(2)}"
    changed, n = re.subn(r"(\d+(?:\.\d+)?)\s*(cm|mm|m|km|degrees? celsius|celsius)\b", repl, text, count=1, flags=re.I)
    if not n:
        return Mutation(FaultClass.QUANTITY_CHANGED, text, True, "No quantity found")
    return Mutation(FaultClass.QUANTITY_CHANGED, changed, True, "Critical quantity altered")


def inject_time_change(text: str) -> Mutation:
    def repl(match: re.Match[str]) -> str:
        hour = int(match.group(1))
        return f"{((hour + 2 - 1) % 12) + 1}{match.group(2)}"
    changed, n = re.subn(r"\b(\d{1,2})(\s*(?:AM|PM))\b", repl, text, count=1, flags=re.I)
    if not n:
        changed, n = re.subn(r"\b(\d{2}):(\d{2})\b", lambda m: f"{(int(m.group(1))+2)%24:02d}:{m.group(2)}", text, count=1)
    return Mutation(FaultClass.TIME_CHANGED, changed, True, "Critical time changed")


def inject_location_change(text: str) -> Mutation:
    replacements = [
        (r"\beastern\b", "western"),
        (r"\bwestern\b", "eastern"),
        (r"\bnorth\b", "south"),
        (r"\bsouth\b", "north"),
        (r"\bZone\s+4\b", "Zone 9"),
    ]
    for pattern, replacement in replacements:
        changed, n = re.subn(pattern, replacement, text, count=1, flags=re.I)
        if n:
            return Mutation(FaultClass.LOCATION_CHANGED, changed, True, "Action-linked location swapped")
    return Mutation(FaultClass.LOCATION_CHANGED, text + " Use the western zone instead.", True, "Location corruption appended")


def inject_action_change(text: str) -> Mutation:
    pairs = [(r"\bshelter\b", "evacuate"), (r"\bevacuate\b", "shelter"), (r"\bstay\s+indoors\b", "leave the area")]
    for pattern, repl in pairs:
        changed, n = re.subn(pattern, repl, text, count=1, flags=re.I)
        if n:
            return Mutation(FaultClass.ACTION_CHANGED, changed, True, "Required protective action changed")
    return Mutation(FaultClass.ACTION_CHANGED, text, True, "No mutable action found")


def inject_action_removed(text: str) -> Mutation:
    patterns = [
        r"(?:Shelter|Stay)\s+(?:indoors|inside)(?:\s+until\s+[^.;]+)?[.;]?",
        r"Evacuate(?:\s+the\s+(?:area|zone))?(?:\s+immediately)?[.;]?",
    ]
    for pattern in patterns:
        changed, n = re.subn(pattern, "", text, count=1, flags=re.I)
        if n:
            return Mutation(FaultClass.ACTION_REMOVED, re.sub(r"\s+", " ", changed).strip(), True, "Required action removed")
    return Mutation(FaultClass.ACTION_REMOVED, text, True, "No removable action found")


def inject_audience_change(text: str) -> Mutation:
    changed, n = re.subn(r"\bresidents\b", "emergency responders", text, count=1, flags=re.I)
    return Mutation(FaultClass.AUDIENCE_CHANGED, changed if n else text + " This applies only to emergency responders.", True, "Target audience changed")


def inject_exception_removed(text: str) -> Mutation:
    changed, n = re.subn(r"\b(?:except|unless)\s+[^.;]+[.;]?", "", text, count=1, flags=re.I)
    return Mutation(FaultClass.EXCEPTION_REMOVED, re.sub(r"\s+", " ", changed).strip(), True, "Exception removed")


def clean_paraphrase(text: str) -> Mutation:
    replacements = [
        (r"\bStay indoors\b", "Shelter indoors"),
        (r"\bShelter indoors\b", "Stay indoors"),
        (r"\bimmediately\b", "right away"),
    ]
    changed = text
    for pattern, repl in replacements:
        candidate, n = re.subn(pattern, repl, changed, count=1, flags=re.I)
        if n:
            changed = candidate
            break
    return Mutation(FaultClass.CLEAN, changed, False, "Meaning-preserving controlled paraphrase")
