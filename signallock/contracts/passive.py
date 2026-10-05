"""Bounded explicit-agent passive grammar; other clauses remain unresolved.

The ordinary extractor owns slot binding. This grammar is not a general translator.
"""
import re

PASSIVE_CUE = re.compile(r"\b(?:must|should|may|can)\s+(?:not\s+)?be\b", re.I)
_ACTOR = r"(?:residents|visitors|drivers|motorists|students|children|adults|hospital staff|hospital patients|emergency personnel)"
_AREA = r"(?:zone\s+[a-z0-9-]+|(?:north|south|east|west)\s+(?:zone|district|area))"
_TIME = r"(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)|noon|midnight)"
_MODIFIERS = (
    rf"(?:\s+(?:by|before|after|until)\s+{_TIME})?"
    r"(?:\s+for\s+\d+(?:\.\d+)?\s+(?:minutes?|hours?))?"
    rf"(?:\s+except\s+for\s+{_ACTOR})?"
    r"(?:\s+if\s+(?:officials|authorities)\s+(?:order|approve)\s+it)?"
)
_DIRECTIVE = re.compile(
    r"\s*(?P<object>(?:the\s+)?(?:tap\s+water|water|bridge|road|roads))\s+"
    r"(?P<modal>must|should|may|can)\s+be\s+(?P<participle>boiled|drunk|avoided)\s+by\s+"
    rf"(?P<actor>{_ACTOR})(?P<area>\s+in\s+{_AREA})?"
    rf"(?P<tail>{_MODIFIERS})\s*[.!]?\s*", re.I,
)
_VERBS = {"boiled": "boil", "drunk": "drink", "avoided": "avoid"}


def active_directive(sentence: str) -> str | None:
    match = _DIRECTIVE.fullmatch(sentence)
    if not match:
        return None
    patient = re.sub(r"^the\s+", "", match["object"], flags=re.I).casefold()
    verb = _VERBS[match["participle"].casefold()]
    if verb in {"boil", "drink"} and patient not in {"water", "tap water"}:
        return None
    return (
        f"{match['actor']}{match['area'] or ''} {match['modal']} "
        f"{verb} {match['object']}{match['tail']}."
    )
