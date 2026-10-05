from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from signallock.contracts.passive import PASSIVE_CUE, active_directive

from signallock.contracts.schema import (
    Action,
    ActionType,
    Certainty,
    EvidenceSpan,
    ExceptionRule,
    Hazard,
    LogicOperator,
    Modality,
    Quantity,
    QuantityRelation,
    SafetyContract,
    Severity,
    TemporalConstraint,
    TemporalOperator,
    Urgency,
)

# Deterministic English development extractor.  The critical design rule is that
# relationships are extracted onto the Action itself instead of only into global bags.
_SENTENCE = re.compile(r".+?(?:[.!?।。！？؟](?=\s|$)|\n|$)", re.UNICODE | re.S)
_CLOCK_VALUE = r"(?:\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?|noon|midnight)"
_WEEKDAY_VALUE = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
_MONTH_VALUE = r"(?:january|february|march|april|may|june|july|august|september|october|november|december)"
_DATE_VALUE = rf"(?:\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH_VALUE}(?:\s+\d{{4}})?)"
_TEMPORAL_VALUE = rf"(?:{_DATE_VALUE}|{_WEEKDAY_VALUE}|{_CLOCK_VALUE})"
_TIME = re.compile(
    rf"\b(no\s+later\s+than|prior\s+to|starting(?:\s+at)?|from|until|by|before|after|at|on)\s+({_TEMPORAL_VALUE})\b",
    re.I,
)
_RELATIVE_TIME_CUE = re.compile(
    r"\b(?:today|tonight|tomorrow|overnight|later\s+today|later\s+tonight|"
    r"this\s+(?:morning|afternoon|evening)|next\s+(?:morning|afternoon|evening|night|week))\b",
    re.I,
)
_UNREPRESENTED_CONDITION_CUE = re.compile(r"\bwhether\b", re.I)
_UNREPRESENTED_DEONTIC_CUE = re.compile(
    r"\b(?:is|are|was|were|be)\s+(?:strictly\s+)?(?:prohibited|forbidden|not\s+(?:permitted|allowed))\b|"
    r"\b(?:prohibited|forbidden)\s+from\b|\bforbidden\s+to\b",
    re.I,
)

_HAZARDS: list[tuple[str, str]] = [
    ("flash_flood", r"\bflash flood(?:ing)?\b"),
    ("flood", r"\bflood(?:ing)?\b"),
    ("wildfire", r"\bwildfire\b"),
    ("cyclone", r"\bcyclone\b"),
    ("extreme_heat", r"\b(?:extreme heat|heatwave|heat wave)\b"),
    ("severe_storm", r"\b(?:severe storm|thunderstorm)\b"),
]

_SEVERITY_WORD = re.compile(r"\b(extreme|severe|moderate|minor)\b", re.I)
_CERTAINTY_WORD = re.compile(r"\b(observed|likely|possible|unlikely)\b", re.I)
_EVENT_SUBJECT = re.compile(
    r"^\s*(?:an?|the)\s+(?P<subject>[a-z][a-z0-9-]*(?:\s+(?:and|or|[a-z][a-z0-9-]*)){0,6}?)\s+"
    r"(?P<predicate>affects?|is\s+affecting|threatens?|is\s+threatening|"
    r"is\s+(?:likely|unlikely|possible)\s+to\s+affect|has\s+occurred|occurred|"
    r"was\s+reported|is\s+reported|has\s+been\s+reported)\b",
    re.I,
)
_CAUSAL_CUE = re.compile(r"\b(?:due\s+to|because\s+of|following)\s+(?:an?\s+|the\s+)?(?P<cause>[^,.;!?]+)", re.I)
_QUANTITY = re.compile(
    r"(?<![\w.])([+-]?(?:(?:\d{1,3}(?:,\d{3})+)|\d+)(?:\.\d+)?)\s*"
    r"(%|percent|cm|centimeters?|centimetres?|mm|millimeters?|millimetres?|m|meters?|metres?|"
    r"km/h|km\s*/\s*h|kilometers?\s+per\s+hour|kilometres?\s+per\s+hour|km|kilometers?|kilometres?|"
    r"°?c|celsius|minutes?|mins?|hours?|hrs?)(?=\s|[.,;!?]|$)",
    re.I,
)
_UNSUPPORTED_OPERATIONAL = re.compile(
    r"\b(?:relocate\s+livestock|keep\s+clear\s+of\s+waterways|remain\s+off\s+bridges|secure\s+loose\s+outdoor\s+objects|isolate\s+the\s+supply|return\s+only\s+when\s+cleared)\b", re.I
)

_OPERATIONAL_CUE = re.compile(
    r"\b(?:must|should|may|can|advised\s+to|urged\s+to|need\s+not|not\s+required|do\s+not|don't|never|avoid|shelter|stay|remain|move|head|disconnect|seek|go|boil|drink|turn|take\s+shelter|keep\s+out|evacuate|leave|monitor|prepare)\b",
    re.I,
)

# English heuristic extraction is intentionally not a multilingual parser.  These
# patterns identify only text that is confidently non-operational metadata; other
# substantive unaccounted-for clauses fail closed to unresolved_operational_text.
_CONFIDENT_NON_OPERATIONAL = [
    re.compile(r"^\s*for\s+(?:more\s+)?information(?:\s+only)?(?:\s*[,.:;-]\s*(?:call|contact|visit|see)\b.*)?[.!?]*\s*$", re.I),
    re.compile(r"^\s*(?:call|contact)\s+[^.!?]+(?:\s+for\s+(?:more\s+)?information)?[.!?]*\s*$", re.I),
    re.compile(r"^\s*visit\s+https?://\S+(?:\s+for\s+[^.!?]+)?[.!?]*\s*$", re.I),
    re.compile(r"^\s*https?://\S+[.!?]*\s*$", re.I),
    re.compile(r"^\s*(?:this\s+)?alert\s+(?:was\s+)?issued\s+by\b.*[.!?]*\s*$", re.I),
    re.compile(r"^\s*source\s*:\s*[^.!?]+[.!?]*\s*$", re.I),
    re.compile(r"^\s*(?:official\s+)?update[.!?]*\s*$", re.I),
    # Meta-language can be adversarial input to a provider, but by itself it is not an
    # emergency-alert action.  Operational meta-prohibitions such as "do not extract"
    # are intentionally not included here and remain covered by the deontic guard.
    re.compile(r"^\s*ignore\s+(?:all\s+|previous\s+)?instructions[.!?]*\s*$", re.I),
    re.compile(r"^\s*return\s+(?:pass|block|review)[.!?]*\s*$", re.I),
    # Narrow metadata-only controls. These classify complete sentences whose ONLY
    # occurrence does not constrain an operational directive/scope.
    re.compile(r"^\s*this\s+is\s+only\s+a\s+test\s+message[.!?]*\s*$", re.I),
    re.compile(r"^\s*administrative\s+use\s+only[.!?]*\s*$", re.I),
    re.compile(r"^\s*(?:this\s+)?(?:phone\s+number|source\s+attribution)\s+is\s+for\s+(?:information|reference)\s+only[.!?]*\s*$", re.I),
]
_STRONG_CLAUSE_BREAK = re.compile(r"\s*(?:;|—|–|--|\u2015)\s*")


def _has_unsupported_english_script_material(text: str) -> bool:
    """Detect letters/numerals the English heuristic does not claim to interpret.

    Latin letters with diacritics remain supported lexical material. Combining marks,
    emoji, punctuation, currency/degree symbols, and typography are not treated as
    unsupported-language evidence. Non-ASCII decimal digits are conservative because
    they can carry operational quantities/times the English normalizer may miss.
    """
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("L"):
            if "LATIN" not in unicodedata.name(char, ""):
                return True
        elif category == "Nd" and ord(char) > 0x7F:
            return True
    return False


def _confidently_non_operational_clause(text: str) -> bool:
    value = text.strip()
    if not value:
        return True
    # Typographic quotation marks around otherwise non-operational metadata are
    # presentation, not a language boundary.
    value = value.strip("\"'“”‘’")
    if not value:
        return True
    # Symbols/emoji/punctuation without letters or decimal digits carry no independently
    # interpreted operational proposition for this extractor.
    if not any(unicodedata.category(ch).startswith("L") or unicodedata.category(ch) == "Nd" for ch in value):
        return True
    return any(pattern.fullmatch(value) for pattern in _CONFIDENT_NON_OPERATIONAL)


def _has_supported_non_action_semantics(text: str, quantities: list[Quantity]) -> bool:
    """Whether a no-action English clause is already represented by typed fields."""
    if quantities:
        return True
    if _known_hazard_matches(text):
        return True
    if _severity_candidates(text)[0] or _certainty_candidates(text)[0]:
        return True
    if _urgency(text) != Urgency.UNKNOWN:
        return True
    # Global audience/area bags are real represented fields even without an action.
    if _audiences(text) or _areas(text):
        return True
    return False


def _substantive_latin_clause(text: str) -> bool:
    """Conservative test for prose that cannot be dismissed as punctuation/labels."""
    words = re.findall(r"[^\W\d_]+(?:[’'-][^\W\d_]+)*", text, re.UNICODE)
    # A short imperative in another Latin-script language can be one word.  Since this
    # extractor cannot establish the language or meaning, any nontrivial unaccounted
    # lexical token is uncertainty rather than presumed harmlessness.
    return any(len(word) >= 3 for word in words)


def _unaccounted_strong_subclause(sentence: str, pending: list["_PendingAction"]) -> str | None:
    """Return an unrepresented clause separated by an explicit strong boundary.

    This does not try to identify a language. It only asks whether a substantive segment
    has no extracted directive and is not confidently non-operational or otherwise typed.
    """
    boundaries = list(_STRONG_CLAUSE_BREAK.finditer(sentence))
    if not boundaries:
        return None
    spans: list[tuple[int, int]] = []
    start = 0
    for boundary in boundaries:
        spans.append((start, boundary.start()))
        start = boundary.end()
    spans.append((start, len(sentence)))
    for seg_start, seg_end in spans:
        segment = sentence[seg_start:seg_end].strip()
        if not segment:
            continue
        overlaps_action = any(not (item.end <= seg_start or item.start >= seg_end) for item in pending)
        if overlaps_action:
            continue
        if _confidently_non_operational_clause(segment):
            continue
        if _has_supported_non_action_semantics(segment, []):
            continue
        if _has_unsupported_english_script_material(segment) or _substantive_latin_clause(segment):
            return segment
    return None


_ENGLISH_RESIDUAL_GRAMMAR = {
    "a", "an", "the", "all", "and", "or", "but", "to", "of", "in", "on", "at", "by", "from", "for", "except",
    "with", "without", "into", "onto", "within", "outside", "inside", "near", "away", "under", "over", "above",
    "below", "before", "after", "until", "through", "during", "because", "due", "following", "if", "unless",
    "when", "whenever", "whether", "provided", "that", "as", "long", "soon", "than", "is", "are", "was", "were",
    "be", "been", "being", "has", "have", "had", "must", "should", "may", "can", "could", "would", "will", "shall",
    "do", "does", "did", "not", "never", "required", "advised", "urged", "need", "residents", "resident", "people",
    "drivers", "motorists", "visitors", "students", "children", "adults", "patients", "staff", "personnel", "emergency",
    "now", "immediately", "right", "once", "today", "tonight", "tomorrow", "later", "this", "next", "morning",
    "afternoon", "evening", "night", "week", "officials", "official", "order", "ordered", "it", "they", "you", "we", "then",
    "more", "less", "greater", "deeper", "least", "most", "exactly", "equal", "water", "depth", "wind", "speed", "temperature", "percent",
    "please", "kindly", "thanks", "thank",
}
_INLINE_INFORMATIONAL = [
    re.compile(r"\bfor\s+(?:more\s+)?information\b.*$", re.I),
    re.compile(r"\bvisit\s+https?://\S+.*$", re.I),
    re.compile(r"\b(?:this\s+)?alert\s+(?:was\s+)?issued\s+by\b.*$", re.I),
    re.compile(r"\bsource\s*:\s*.*$", re.I),
]


_RESTRICTIVE_SCOPE_CUE = re.compile(
    r"\b(?:only|solely|exclusively)\b|\b(?:restricted|limited)\s+to\b",
    re.I,
)


def _span_contains(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(left <= start and end <= right for left, right in spans)


def _adjacent_only_spans(sentence_view: str, pending: list["_PendingAction"]) -> list[tuple[int, int]]:
    """Return ONLY tokens whose restrictive effect is represented by an action time.

    Existing temporal semantics already encode constraints such as BEFORE/AFTER/AT.
    For forms like "only after 6 PM" or "after 6 PM only", the product treats the
    restriction as the same represented temporal relation.  This helper prevents the
    coverage guard from turning those supported temporal forms into blanket REVIEW.
    """
    out: list[tuple[int, int]] = []
    temporal_spans = [span for item in pending for span in item.temporal_spans]
    for match in re.finditer(r"\bonly\b", sentence_view, re.I):
        for start, end in temporal_spans:
            if match.end() <= start:
                between = sentence_view[match.end():start]
                if not between.strip(" \t"):
                    out.append(match.span())
                    break
            elif end <= match.start():
                between = sentence_view[end:match.start()]
                if not between.strip(" \t"):
                    out.append(match.span())
                    break
    return out


def _unrepresented_restrictive_scope(sentence: str, pending: list["_PendingAction"]) -> str | None:
    """Preserve operational restriction cues that are not represented by typed semantics.

    This is a coverage guard, not a quantifier parser.  It deliberately does not guess
    the scope of audience/area/action exclusivity.  Represented `only if` conditions and
    represented temporal restrictions are excluded; confidently informational sentences
    are excluded.  Remaining operational restriction cues fail closed to unresolved text.
    """
    if _confidently_non_operational_clause(sentence):
        return None

    view = _lexical(sentence)
    condition_spans = _condition_spans(view, pending)
    temporal_only_spans = _adjacent_only_spans(view, pending)

    operational_context = bool(
        pending
        or _audiences(sentence)
        or _areas(sentence)
        or _QUANTITY.search(view)
        or _OPERATIONAL_CUE.search(view)
    )
    if not operational_context:
        return None

    for match in _RESTRICTIVE_SCOPE_CUE.finditer(view):
        token = match.group(0).casefold()
        if token == "only":
            if _span_contains(condition_spans, match.start(), match.end()):
                continue
            if _span_contains(temporal_only_spans, match.start(), match.end()):
                continue
        # `solely`, `exclusively`, `restricted to`, and `limited to` are deliberately
        # not normalized into audience identity.  If operational, they remain unresolved
        # until the schema has an explicit restriction representation.
        return sentence.strip()
    return None


def _unaccounted_latin_residual(sentence: str, pending: list["_PendingAction"]) -> str | None:
    """Detect substantial Latin-script residue after represented English semantics.

    This is a coverage check, not language identification: it masks text already
    accounted for by deterministic action/scope/time/quantity/condition/hazard fields
    and common English grammatical glue. Two or more remaining lower-case lexical
    tokens are treated as unestablished meaning and routed to REVIEW.
    """
    if not pending:
        return None
    chars = list(sentence)

    def mask(start: int, end: int) -> None:
        for idx in range(max(0, start), min(len(chars), end)):
            chars[idx] = " "

    def mask_pattern(pattern: re.Pattern[str]) -> None:
        for match in pattern.finditer(sentence):
            mask(match.start(), match.end())

    for item in pending:
        mask(item.start, item.end)
        for temporal_start, temporal_end in item.temporal_spans:
            mask(temporal_start, temporal_end)
        for value in (
            item.action.condition,
            item.action.deadline,
            *item.action.scoped_audience,
            *item.action.scoped_areas,
            *item.action.bound_exceptions,
        ):
            if not value:
                continue
            for match in re.finditer(re.escape(value), sentence, re.I):
                mask(match.start(), match.end())
    for only_start, only_end in _adjacent_only_spans(sentence, pending):
        mask(only_start, only_end)

    for pattern, _ in _AUDIENCE_PATTERNS:
        mask_pattern(pattern)
    mask_pattern(_GENERIC_AUDIENCE)
    mask_pattern(_AREA)
    mask_pattern(_OPEN_AREA)
    mask_pattern(_QUANTITY)
    mask_pattern(_SEVERITY_WORD)
    mask_pattern(_CERTAINTY_WORD)
    for _, pattern in _HAZARDS:
        mask_pattern(re.compile(pattern, re.I))
    for pattern in _INLINE_INFORMATIONAL:
        mask_pattern(pattern)

    residual = "".join(chars)
    unknown: list[str] = []
    for match in re.finditer(r"[^\W\d_]+(?:[’'-][^\W\d_]+)*", residual, re.UNICODE):
        token = match.group(0)
        folded = token.casefold()
        if folded in _ENGLISH_RESIDUAL_GRAMMAR:
            continue
        # Post-directive names can be unrepresented destinations/objects.
        # Preserve the existing subject-name handling before the first action.
        if (token[:1].isupper() and match.start() < min(item.start for item in pending)
                and not re.search(r"\b(?:in|of|from|within|at)\s+", residual[:match.start()], re.I)):
            continue
        unknown.append(token)

    if any(len(token) >= 3 for token in unknown):
        return sentence.strip()
    return None

# Make visually equivalent separators lexically equivalent without changing string length;
# evidence offsets continue to address the original source text.
_CHAR_TRANSLATION = str.maketrans({
    "‑": "-", "–": "-", "—": "-", "−": "-", "‐": "-", "‒": "-", "﹘": "-", "－": "-",
    "\u200b": " ", "\u200c": " ", "\u200d": " ", "\ufeff": " ",
})

_AUDIENCE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?<![\w-])non[-\s]?residents(?![\w-])", re.I), "non-residents"),
    (re.compile(r"(?<![\w-])(?:all\s+)?residents(?![\w-])", re.I), "residents"),
    (re.compile(r"\bpeople\s+living(?:\s+in\s+the\s+area)?\b", re.I), "residents"),
    (re.compile(r"\bvisitors\b", re.I), "visitors"),
    (re.compile(r"\b(?:drivers|motorists)\b", re.I), "drivers"),
    (re.compile(r"\bstudents\b", re.I), "students"),
    (re.compile(r"(?<![\w-])non[-\s]?emergency\s+personnel(?![\w-])", re.I), "non-emergency personnel"),
    (re.compile(r"\bemergency\s+(?:personnel|responders|staff)\b", re.I), "emergency personnel"),
]

_AREA = re.compile(
    r"\b((?:(?:north|south|east|west|northern|southern|eastern|western)\s+"
    r"(?:[a-z]+\s+){0,2}?(?:district|zone|area))|(?:zone\s+[a-z0-9-]+))\b",
    re.I,
)

_GENERIC_AUDIENCE = re.compile(
    r"(?:^|[.!?]\s*)([A-Za-z][A-Za-z-]*(?:\s+[A-Za-z][A-Za-z-]*){0,2}?)(?:\s+in\s+[^,.;]+)?\s+"
    r"(?:must|should|may|can|are\s+advised\s+to|are\s+urged\s+to|are\s+required\s+to)\b", re.I
)
_OPEN_AREA = re.compile(
    r"\bin\s+((?:Zone\s+[A-Za-z0-9-]+)|(?:[A-Z][\w-]+(?:\s+[A-Z][\w-]+){0,3}))\s+"
    r"(?=(?:must|should|may|can|are\s+advised\s+to|are\s+urged\s+to|are\s+required\s+to)\b)"
)

_PROHIBITION = re.compile(r"\b(?:do\s+not|don't|never|must\s+not)\s+([a-z]+)(?:\s+([^.;,!]+))?", re.I)
_KEEP_OUT = re.compile(r"\bkeep\s+out\s+of\s+(?:the\s+)?([^.;,!]+)", re.I)
_STAY_AWAY = re.compile(r"\bstay\s+away\s+from\s+(?:the\s+)?([^.;,!]+)", re.I)
_NO_EVAC = re.compile(r"\bno\s+evacuation\s+is(?:\s+currently)?\s+required\b", re.I)

_REQUIRED_PATTERNS: list[tuple[ActionType, str, re.Pattern[str], str]] = [
    (ActionType.SHELTER, "shelter", re.compile(r"\b(?:shelter|stay|remain)\s+(?:indoors|inside)\b", re.I), "indoors"),
    (ActionType.SHELTER, "shelter", re.compile(r"\btake\s+shelter\s+(?:on|in)\s+(?:the\s+)?([^.;,!]+)", re.I), "capture_destination"),
    (ActionType.EVACUATE, "evacuate", re.compile(r"\b(?:evacuate|leave)(?:\s+the\s+(?:area|zone))?\b", re.I), ""),
    (ActionType.EXECUTE, "move", re.compile(r"\b(?:move|head)\s+to\s+(higher|lower)\s+ground\b", re.I), "capture_destination"),
    (ActionType.EXECUTE, "boil", re.compile(r"\bboil\s+(?:the\s+)?(tap\s+water|water)\b", re.I), "capture_object"),
    (ActionType.EXECUTE, "drink", re.compile(r"\bdrink\s+(?:the\s+)?(tap\s+water|water)\b", re.I), "capture_object"),
    (ActionType.EXECUTE, "turn off", re.compile(r"\bturn(?:ing)?\s+off\s+(?:the\s+)?([^.;,!]+)", re.I), "capture_object"),
    (ActionType.EXECUTE, "turn off", re.compile(r"\bdisconnect\s+(?:the\s+)?([^.;,!]+)", re.I), "capture_object"),
    (ActionType.EXECUTE, "turn on", re.compile(r"\bturn\s+on\s+(?:the\s+)?([^.;,!]+)", re.I), "capture_object"),
    (ActionType.EXECUTE, "stand", re.compile(r"\bstand\s+near\s+(?:the\s+)?([^.;,!]+)", re.I), "capture_object"),
    (ActionType.AVOID, "avoid", re.compile(r"\bavoid\s+(?:the\s+)?(roads?|travel|water|bridges?|tunnels?|underpasses?)\b", re.I), "capture_object"),
]


def _lexical(text: str) -> str:
    return text.translate(_CHAR_TRANSLATION)


def _span(text: str, start: int, end: int) -> EvidenceSpan:
    return EvidenceSpan(quote=text[start:end], start_char=start, end_char=end)


def _clean_object(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip(" ,")
    value = re.sub(r"\s+with\s+(?:more|less)\s+than\s+.+$", "", value, flags=re.I)
    value = re.sub(r"\s+deeper\s+than\s+.+$", "", value, flags=re.I)
    return value.strip() or None


def _quantity_meaning(sentence: str, match: re.Match[str]) -> str | None:
    window = sentence[max(0, match.start() - 70): min(len(sentence), match.end() + 70)].casefold()
    if "water" in window or "flood" in window:
        return "water depth"
    if "wind" in window:
        return "wind speed"
    if "boil" in window:
        return "boil duration"
    if "temperature" in window or re.search(r"\bbelow\b|\babove\b", window):
        return "temperature"
    return None


def _quantity_relation(sentence: str, match: re.Match[str]) -> QuantityRelation:
    prefix = sentence[max(0, match.start() - 32):match.start()].casefold()
    if re.search(r"(?:at\s+least|no\s+less\s+than)\s*$", prefix):
        return QuantityRelation.GREATER_OR_EQUAL
    if re.search(r"(?:at\s+most|no\s+more\s+than)\s*$", prefix):
        return QuantityRelation.LESS_OR_EQUAL
    if re.search(r"(?:more\s+than|greater\s+than|deeper\s+than|above|over)\s*$", prefix):
        return QuantityRelation.GREATER_THAN
    if re.search(r"(?:less\s+than|below|under)\s*$", prefix):
        return QuantityRelation.LESS_THAN
    if re.search(r"(?:exactly|equal\s+to)\s*$", prefix):
        return QuantityRelation.EQUAL
    return QuantityRelation.UNKNOWN


def _urgency(text: str) -> Urgency:
    if re.search(r"\b(?:immediately|right away|at once|now)\b", text, re.I):
        return Urgency.IMMEDIATE
    future_view = re.sub(r"\bno\s+later\s+than\b", "", text, flags=re.I)
    if re.search(r"\b(?:tomorrow|later|in the future)\b", future_view, re.I):
        return Urgency.FUTURE
    return Urgency.UNKNOWN


def _known_hazard_matches(text: str) -> list[tuple[str, re.Match[str]]]:
    view = _lexical(text)
    out: list[tuple[str, re.Match[str]]] = []
    for name, pattern in _HAZARDS:
        match = re.search(pattern, view, re.I)
        if match:
            out.append((name, match))
    return out


def _strip_supported_event_words(value: str) -> str:
    """Remove only semantics this extractor can independently represent.

    Any remaining noun phrase from an event/hazard position is treated as
    operationally meaningful but unsupported rather than guessed into Hazard.type.
    """
    residual = " " + _lexical(value).casefold() + " "
    for _, pattern in _HAZARDS:
        residual = re.sub(pattern, " ", residual, flags=re.I)
    residual = _SEVERITY_WORD.sub(" ", residual)
    residual = _CERTAINTY_WORD.sub(" ", residual)
    residual = re.sub(r"\b(?:and|or|the|a|an)\b", " ", residual, flags=re.I)
    return " ".join(residual.split())


def _unsupported_event_identity(sentence: str, *, has_pending_action: bool) -> bool:
    view = _lexical(sentence)
    subject = _EVENT_SUBJECT.search(view)
    if subject and _strip_supported_event_words(subject.group("subject")):
        return True
    if has_pending_action:
        for match in _CAUSAL_CUE.finditer(view):
            if _strip_supported_event_words(match.group("cause")):
                return True
    return False


def _severity_candidates(text: str) -> tuple[set[Severity], list[str]]:
    values: set[Severity] = set()
    uncertain_clauses: list[str] = []
    for sentence_match in _SENTENCE.finditer(text):
        sentence = sentence_match.group(0)
        view = _lexical(sentence)
        local: set[Severity] = set()
        for match in re.finditer(r"\bseverity\s*(?::|=|is)?\s*(extreme|severe|moderate|minor)\b", view, re.I):
            local.add(Severity(match.group(1).title()))
        hazard_matches = _known_hazard_matches(sentence)
        for word in _SEVERITY_WORD.finditer(view):
            # A modifier immediately preceding a recognized hazard is an explicit
            # severity only when it is not lexically part of that hazard's name.
            following = view[word.end():].lstrip()
            for hazard_name, hazard_match in hazard_matches:
                if hazard_match.start() < word.start():
                    continue
                between = view[word.end():hazard_match.start()]
                if between.strip():
                    continue
                if hazard_name in {"extreme_heat", "severe_storm"} and hazard_match.start() == word.start():
                    continue
                local.add(Severity(word.group(1).title()))
        values.update(local)
        if _SEVERITY_WORD.search(view) and hazard_matches and not local:
            lexical_hazard_words = {
                (hm.start(), hm.end())
                for name, hm in hazard_matches
                if name in {"extreme_heat", "severe_storm"}
            }
            standalone_cues = [
                word for word in _SEVERITY_WORD.finditer(view)
                if not any(start <= word.start() and word.end() <= end for start, end in lexical_hazard_words)
            ]
            if standalone_cues:
                # A severity-looking cue occurred in a hazard proposition but could
                # not be safely separated from the represented hazard identity.
                uncertain_clauses.append(sentence.strip())
    return values, uncertain_clauses


def _certainty_candidates(text: str) -> tuple[set[Certainty], list[str]]:
    values: set[Certainty] = set()
    uncertain_clauses: list[str] = []
    for sentence_match in _SENTENCE.finditer(text):
        sentence = sentence_match.group(0)
        view = _lexical(sentence)
        local: set[Certainty] = set()
        for match in re.finditer(r"\bcertainty\s*(?::|=|is)?\s*(observed|likely|possible|unlikely)\b", view, re.I):
            local.add(Certainty(match.group(1).title()))
        hazard_matches = _known_hazard_matches(sentence)
        if hazard_matches:
            for word in _CERTAINTY_WORD.finditer(view):
                prefix = view[max(0, word.start() - 12):word.start()]
                if re.search(r"\b(?:if|when|where)\s*$", prefix, re.I):
                    continue
                # Safe forms: "likely wildfire" or "wildfire is likely to ...".
                before_hazard = any(
                    word.end() <= hm.start() and not view[word.end():hm.start()].strip()
                    for _, hm in hazard_matches
                )
                after_hazard = any(
                    hm.end() <= word.start()
                    and re.fullmatch(r"\s+(?:is|was|are|were)\s+", view[hm.end():word.start()], re.I)
                    and bool(re.match(r"\s*(?:to\b|[.,;!?]|$)", view[word.end():], re.I))
                    for _, hm in hazard_matches
                )
                if before_hazard or after_hazard:
                    local.add(Certainty(word.group(1).title()))
        values.update(local)
        if _CERTAINTY_WORD.search(view) and hazard_matches and not local:
            # Do not guess from phrases such as "if possible"; surface the sentence
            # only when the certainty-looking word is close to the hazard proposition.
            for _, hm in hazard_matches:
                if any(abs(word.start() - hm.end()) <= 40 for word in _CERTAINTY_WORD.finditer(view)):
                    uncertain_clauses.append(sentence.strip())
                    break
    return values, uncertain_clauses


def _enum_or_unknown(values: set, unknown):
    return next(iter(values)) if len(values) == 1 else unknown


def _has_unrepresented_severity_cue(sentence: str) -> bool:
    values, _ = _severity_candidates(sentence)
    if values:
        return False
    view = _lexical(sentence)
    lexical_hazard_spans = [
        hm.span()
        for name, hm in _known_hazard_matches(sentence)
        if name in {"extreme_heat", "severe_storm"}
    ]
    return any(
        not any(start <= word.start() and word.end() <= end for start, end in lexical_hazard_spans)
        for word in _SEVERITY_WORD.finditer(view)
    )


def _has_unrepresented_certainty_cue(sentence: str) -> bool:
    values, _ = _certainty_candidates(sentence)
    if values:
        return False
    view = _lexical(sentence)
    # "if/when/where/as soon as possible" is a condition/feasibility phrase, not
    # CAP-style certainty. It is already preserved by condition extraction where
    # applicable and must not be promoted to a global certainty claim.
    view = re.sub(r"\b(?:if|when|where)\s+possible\b|\bas\s+soon\s+as\s+possible\b", " ", view, flags=re.I)
    return bool(_CERTAINTY_WORD.search(view))


def _canonical_exception(raw: str) -> str:
    value = raw.strip(" ,")
    value = re.sub(r"^unless\s+(?:you\s+are\s+)?", "except ", value, flags=re.I)
    value = re.sub(r"^except\s+for\s+", "except ", value, flags=re.I)
    value = re.sub(r"\bemergency\s+(?:responders|staff)\b", "emergency personnel", value, flags=re.I)
    return " ".join(value.split())


def _audiences(text: str) -> list[str]:
    view = _lexical(text)
    out: list[str] = []
    for pattern, canonical in _AUDIENCE_PATTERNS:
        if pattern.search(view) and canonical.casefold() not in {x.casefold() for x in out}:
            out.append(canonical)
    # Conservative open-vocabulary subject capture. Known aliases win; only fall
    # back to the raw subject when the sentence has no recognized audience.
    if not out:
        for match in _GENERIC_AUDIENCE.finditer(text):
            phrase = " ".join(match.group(1).strip().split())
            phrase = re.sub(r"^(?:the|all)\s+", "", phrase, flags=re.I)
            if phrase and phrase.casefold() not in {x.casefold() for x in out}:
                out.append(phrase.casefold())
    return out


def _areas(text: str) -> list[str]:
    view = _lexical(text)
    out: list[str] = []
    for match in _AREA.finditer(view):
        loc = text[match.start(1):match.end(1)].strip()
        if loc.casefold() not in {x.casefold() for x in out}:
            out.append(loc)
    for match in _OPEN_AREA.finditer(text):
        loc = " ".join(match.group(1).strip().split())
        if loc.casefold() not in {x.casefold() for x in out}:
            out.append(loc)
    return out

def _dedupe_text(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = " ".join(value.strip(" ,").split())
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _area_mentions(text: str) -> list[tuple[int, str]]:
    mentions: list[tuple[int, str]] = []
    view = _lexical(text)
    for m in _AREA.finditer(view):
        mentions.append((m.start(1), text[m.start(1):m.end(1)].strip()))
    for m in _OPEN_AREA.finditer(text):
        mentions.append((m.start(1), " ".join(m.group(1).strip().split())))
    return mentions


def _modality(sentence_view: str, action_start: int, *, prohibited: bool = False) -> Modality:
    if prohibited:
        return Modality.PROHIBITED
    prefix = sentence_view[max(0, action_start - 120):action_start].casefold()
    if re.search(r"(?:not\s+required\s+to|need\s+not|not\s+advised\s+to)\s*$", prefix):
        return Modality.NOT_REQUIRED
    if re.search(r"(?:\bmay\s+|\bcan\s+)$", prefix):
        return Modality.MAY
    if re.search(r"(?:\bshould\s+|\badvised\s+to\s+|\burged\s+to\s+)$", prefix):
        return Modality.SHOULD
    if re.search(r"(?:\bmust\s+|\brequired\s+to\s+)$", prefix):
        return Modality.MUST
    # Bare imperatives and coordinated imperative clauses remain commands.
    trimmed = prefix.strip()
    if not trimmed or trimmed.endswith((",", ";", ":")) or re.search(r"\b(?:then|after)\s*$", trimmed):
        return Modality.MUST
    if re.search(r"\b(?:residents|people|drivers|motorists|children|adults|patients|staff)\b", trimmed):
        return Modality.MUST
    return Modality.UNKNOWN


def _condition(sentence_view: str, action_start: int, action_end: int) -> str | None:
    # These introducers express a trigger/guard that the existing free-text
    # condition slot can preserve without pretending they are interchangeable.
    lead_intro = r"(?:only\s+if|if|unless|whenever|when|provided\s+that|as\s+long\s+as)"
    lead = re.match(rf"\s*({lead_intro}\s+[^,;]+)\s*[,;]", sentence_view, re.I)
    if lead and lead.end() <= action_end + 120:
        return " ".join(lead.group(1).strip().split())
    tail = sentence_view[action_end:]
    # Tail "unless" remains represented by the existing exception model; parsing it
    # a second time as a condition would break safe except/unless paraphrases.
    tail_intro = r"(?:only\s+if|if|whenever|when|provided\s+that|as\s+long\s+as)"
    # Capture to the sentence terminator, not the first dot: decimal quantities such
    # as 0.3 m must remain intact.  "whether" is deliberately excluded because the
    # current condition model cannot safely normalize its non-trigger semantics.
    post = re.search(rf"\b({tail_intro}\s+.+?)(?=[!?]?$|\.$)", tail.strip(), re.I)
    if post and post.start() < 80:
        value = post.group(1).strip().rstrip(".!?").strip()
        return " ".join(value.split())
    return None


@dataclass(frozen=True, slots=True)
class _TemporalOccurrence:
    start: int
    end: int
    operator: TemporalOperator
    time: str


def _temporal_operator(raw: str) -> TemporalOperator:
    normalized = " ".join(raw.casefold().split())
    mapped = {
        "no later than": TemporalOperator.BY,
        "prior to": TemporalOperator.BEFORE,
        "starting": TemporalOperator.STARTING,
        "starting at": TemporalOperator.STARTING,
        "from": TemporalOperator.STARTING,
        "at": TemporalOperator.AT,
        "on": TemporalOperator.ON,
    }.get(normalized)
    return mapped if mapped is not None else TemporalOperator(normalized.upper())


def _temporal_occurrences(sentence_view: str) -> list[_TemporalOccurrence]:
    return [
        _TemporalOccurrence(
            start=match.start(),
            end=match.end(),
            operator=_temporal_operator(match.group(1)),
            time=match.group(2),
        )
        for match in _TIME.finditer(sentence_view)
    ]


def _time_constraints(sentence_view: str, action_end: int) -> list[TemporalConstraint]:
    """Legacy post-action view used by older unit callers.

    Production extraction binds occurrences after all actions in the sentence are known,
    so temporal scope is not inferred from a blind tail scan.
    """
    out: list[TemporalConstraint] = []
    for occurrence in _temporal_occurrences(sentence_view):
        if occurrence.start < action_end:
            continue
        if occurrence.start - action_end >= 120:
            break
        out.append(TemporalConstraint(operator=occurrence.operator, time=occurrence.time))
    return out


def _time_constraint(sentence_view: str, action_end: int) -> tuple[str | None, TemporalOperator | None]:
    constraints = _time_constraints(sentence_view, action_end)
    if not constraints:
        return None, None
    return constraints[0].time, constraints[0].operator


def _sentence_logic(sentence_view: str, action_spans: list[tuple[int, int]]) -> LogicOperator:
    if len(action_spans) < 2:
        return LogicOperator.SINGLE
    connectors = " ".join(sentence_view[a[1]:b[0]].casefold() for a, b in zip(action_spans, action_spans[1:]))
    if re.search(r"\b(?:or|either)\b", connectors):
        return LogicOperator.OR
    if re.search(r"\band\b", connectors):
        return LogicOperator.AND
    return LogicOperator.SINGLE


def _explicit_sequence(sentence_view: str, action_spans: list[tuple[int, int]]) -> bool:
    if len(action_spans) < 2:
        return False
    if re.match(r"\s*after\b", sentence_view, re.I):
        return True
    return any(re.search(r"\b(?:then|next|afterwards|first)\b", sentence_view[a[1]:b[0]], re.I) for a, b in zip(action_spans, action_spans[1:]))


@dataclass(slots=True)
class _PendingAction:
    action: Action
    start: int
    end: int
    temporal_spans: list[tuple[int, int]]


def _condition_spans(sentence_view: str, pending: list[_PendingAction]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for item in pending:
        if not item.action.condition:
            continue
        for match in re.finditer(re.escape(item.action.condition), sentence_view, re.I):
            spans.append(match.span())
    return spans


def _strong_clause_bounds(sentence_view: str, position: int) -> tuple[int, int]:
    left = 0
    right = len(sentence_view)
    for match in _STRONG_CLAUSE_BREAK.finditer(sentence_view):
        if match.end() <= position:
            left = match.end()
            continue
        if match.start() >= position:
            right = match.start()
            break
    return left, right


def _bind_temporal_occurrences(sentence_view: str, pending: list[_PendingAction]) -> None:
    """Bind recognized time phrases only when their directive scope is deterministic.

    A matched `_TIME` occurrence is not considered consumed merely because the regex
    recognized it.  Prefix forms bind to a single action in the same strong clause;
    suffix forms bind to the nearest preceding action in that clause.  Times embedded
    in a represented condition stay in the condition instead of becoming action time.
    Anything else remains unbound so residual coverage can route it to REVIEW.
    """
    if not pending:
        return

    condition_spans = _condition_spans(sentence_view, pending)
    actions = sorted(pending, key=lambda item: (item.start, item.end))

    for occurrence in _temporal_occurrences(sentence_view):
        if any(start <= occurrence.start and occurrence.end <= end for start, end in condition_spans):
            continue

        clause_start, clause_end = _strong_clause_bounds(sentence_view, occurrence.start)
        clause_actions = [item for item in actions if clause_start <= item.start < clause_end]
        if not clause_actions:
            continue

        preceding = [item for item in clause_actions if item.end <= occurrence.start]
        following = [item for item in clause_actions if item.start >= occurrence.end]
        target: _PendingAction | None = None

        # A suffix time belongs to the closest preceding directive only when it occurs
        # before the next directive in the same clause. This preserves the established
        # post-action behavior without attaching one suffix to every action in a sentence.
        if preceding:
            nearest_preceding = max(preceding, key=lambda item: item.end)
            next_after_time = min(following, key=lambda item: item.start) if following else None
            if occurrence.start - nearest_preceding.end < 120 and (
                next_after_time is None or occurrence.end <= next_after_time.start
            ):
                target = nearest_preceding

        # A clause-leading prefix may bind forward only when there is exactly one action
        # in that strong clause. Multiple actions make prefix scope ambiguous and the
        # occurrence is intentionally left unresolved.
        if target is None and following and len(clause_actions) == 1:
            nearest_following = min(following, key=lambda item: item.start)
            prefix = sentence_view[clause_start:occurrence.start]
            between = sentence_view[occurrence.end:nearest_following.start]
            prefix_is_clause_leading = not re.search(r"[A-Za-z0-9]", prefix)
            if prefix_is_clause_leading and len(between) < 120:
                target = nearest_following

        if target is None:
            continue

        constraint = TemporalConstraint(operator=occurrence.operator, time=occurrence.time)
        if constraint not in target.action.temporal_constraints:
            target.action.temporal_constraints.append(constraint)
        if target.action.temporal_operator is None:
            target.action.temporal_operator = occurrence.operator
        if target.action.deadline is None:
            target.action.deadline = occurrence.time
        target.temporal_spans.append((occurrence.start, occurrence.end))


def _unrepresented_temporal_occurrence(sentence_view: str, pending: list[_PendingAction]) -> str | None:
    represented = [span for item in pending for span in item.temporal_spans]
    represented.extend(_condition_spans(sentence_view, pending))
    for occurrence in _temporal_occurrences(sentence_view):
        if any(start <= occurrence.start and occurrence.end <= end for start, end in represented):
            continue
        return sentence_view[occurrence.start:occurrence.end].strip()
    return None


@dataclass(slots=True)
class HeuristicExtractor:
    """Conservative English extractor with relation-aware scoped directives."""

    def extract(self, text: str, *, language: str = "en", source_id: str | None = None) -> SafetyContract:
        if not text.strip():
            raise ValueError("alert text is empty")
        if language.split("-")[0].lower() != "en":
            raise ValueError("HeuristicExtractor supports English only")

        required: list[Action] = []
        prohibited: list[Action] = []
        quantities: list[Quantity] = []
        exceptions: list[ExceptionRule] = []
        unresolved: list[str] = []

        for sentence_index, sentence_match in enumerate(_SENTENCE.finditer(text)):
            sentence = sentence_match.group(0)
            view = _lexical(sentence)
            sent_start = sentence_match.start()
            if PASSIVE_CUE.search(view):
                active = active_directive(view)
                if active is None:
                    unresolved.append(sentence.strip())
                    continue
                parsed = self.extract(active, language=language)
                # Rewritten offsets cannot serve as provenance. Use the complete
                # original clause for each extracted slot after transposition.
                evidence = _span(text, sent_start, sentence_match.end()).model_dump()

                def original_evidence(value):
                    if isinstance(value, dict):
                        return {k: evidence if k == "evidence" and v is not None else original_evidence(v)
                                for k, v in value.items()}
                    if isinstance(value, list):
                        return [original_evidence(v) for v in value]
                    return value

                parsed = SafetyContract.model_validate(original_evidence(parsed.model_dump()))
                required.extend(parsed.required_actions)
                prohibited.extend(parsed.prohibited_actions)
                quantities.extend(parsed.quantities)
                exceptions.extend(parsed.exceptions)
                if parsed.unresolved_operational_text:
                    unresolved.append(sentence.strip())
                continue
            pending: list[_PendingAction] = []
            prohibited_spans: list[tuple[int, int]] = []

            sentence_audiences = _audiences(sentence)
            sentence_areas = _areas(sentence)

            sentence_quantities: list[Quantity] = []
            quantity_local_spans: list[tuple[int, int]] = []
            for qm in _QUANTITY.finditer(view):
                raw_value = qm.group(1).replace(",", "")
                unit = re.sub(r"\s*/\s*", "/", qm.group(2))
                start, end = sent_start + qm.start(), sent_start + qm.end()
                q = Quantity(
                    value=float(raw_value),
                    unit=unit,
                    relation=_quantity_relation(view, qm),
                    meaning=_quantity_meaning(view, qm),
                    evidence=_span(text, start, end),
                )
                sentence_quantities.append(q)
                quantity_local_spans.append(qm.span())
                quantities.append(q)

            # Explicit prohibitions first so positive patterns cannot double count them.
            for match in _NO_EVAC.finditer(view):
                start, end = sent_start + match.start(), sent_start + match.end()
                prohibited_spans.append(match.span())
                pending.append(_PendingAction(Action(
                    type=ActionType.EVACUATE,
                    verb="evacuate",
                    negated=True,
                    modality=Modality.PROHIBITED,
                    scoped_audience=sentence_audiences,
                    scoped_areas=sentence_areas,
                    evidence=_span(text, start, end),
                ), match.start(), match.end(), []))

            for pattern, verb in [(_KEEP_OUT, "enter"), (_STAY_AWAY, "approach")]:
                for match in pattern.finditer(view):
                    start, end = sent_start + match.start(), sent_start + match.end()
                    prohibited_spans.append(match.span())
                    pending.append(_PendingAction(Action(
                        type=ActionType.AVOID,
                        verb=verb,
                        object=_clean_object(sentence[match.start(1):match.end(1)]),
                        negated=True,
                        modality=Modality.PROHIBITED,
                        scoped_audience=sentence_audiences,
                        scoped_areas=sentence_areas,
                        evidence=_span(text, start, end),
                    ), match.start(), match.end(), []))

            for match in _PROHIBITION.finditer(view):
                if any(not (match.end() <= s or match.start() >= e) for s, e in prohibited_spans):
                    continue
                verb = match.group(1).casefold()
                obj = _clean_object(sentence[match.start(2):match.end(2)] if match.lastindex and match.group(2) else None)
                action_type = ActionType.AVOID if verb in {"enter", "use", "drive", "approach", "cross"} else ActionType.OTHER
                start, end = sent_start + match.start(), sent_start + match.end()
                prohibited_spans.append(match.span())
                pending.append(_PendingAction(Action(
                    type=action_type,
                    verb=verb,
                    object=obj,
                    negated=True,
                    modality=Modality.PROHIBITED,
                    scoped_audience=sentence_audiences,
                    scoped_areas=sentence_areas,
                    evidence=_span(text, start, end),
                ), match.start(), match.end(), []))

            def overlaps_prohibition(start: int, end: int) -> bool:
                return any(not (end <= ps or start >= pe) for ps, pe in prohibited_spans)

            for action_type, canonical_verb, pattern, capture_mode in _REQUIRED_PATTERNS:
                for match in pattern.finditer(view):
                    if overlaps_prohibition(match.start(), match.end()):
                        continue
                    obj = destination = None
                    if capture_mode == "capture_object" and match.lastindex:
                        obj = _clean_object(sentence[match.start(1):match.end(1)])
                    elif capture_mode == "capture_destination" and match.lastindex:
                        destination = _clean_object(sentence[match.start(1):match.end(1)])
                    elif capture_mode:
                        destination = capture_mode

                    temporal_constraints: list[TemporalConstraint] = []
                    deadline = None
                    temporal_operator = None
                    condition = _condition(view, match.start(), match.end())
                    if canonical_verb == "drink" and re.search(r"\bwithout\s+boiling\b", view[match.end():], re.I):
                        condition = "without boiling"

                    start, end = sent_start + match.start(), sent_start + match.end()
                    pending.append(_PendingAction(Action(
                        type=action_type,
                        verb=canonical_verb,
                        object=obj,
                        destination=destination,
                        condition=condition,
                        deadline=deadline,
                        modality=_modality(view, match.start()),
                        scoped_audience=list(sentence_audiences),
                        scoped_areas=list(sentence_areas),
                        temporal_operator=temporal_operator,
                        temporal_constraints=temporal_constraints,
                        evidence=_span(text, start, end),
                    ), match.start(), match.end(), []))

            pending.sort(key=lambda x: (x.start, x.end))

            # If a sentence has multiple distinct audiences/areas, bind each directive to
            # the closest preceding mention rather than copying the whole sentence set.
            if len(sentence_audiences) > 1 or len(sentence_areas) > 1:
                aud_mentions: list[tuple[int, str]] = []
                for pattern, canonical in _AUDIENCE_PATTERNS:
                    for m in pattern.finditer(view):
                        aud_mentions.append((m.start(), canonical))
                area_mentions = _area_mentions(sentence)
                for item in pending:
                    before_aud = [x for x in aud_mentions if x[0] <= item.start]
                    before_area = [x for x in area_mentions if x[0] <= item.start]
                    if before_aud:
                        item.action.scoped_audience = [max(before_aud, key=lambda x: x[0])[1]]
                    if before_area:
                        item.action.scoped_areas = [max(before_area, key=lambda x: x[0])[1]]

            _bind_temporal_occurrences(view, pending)

            spans = [(x.start, x.end) for x in pending if not x.action.negated]
            if len(spans) >= 3 and re.search(r"\band\b", view, re.I) and re.search(r"\bor\b", view, re.I):
                # The flat contract graph cannot faithfully encode nested Boolean groups.
                unresolved.append(sentence.strip())
            logic = _sentence_logic(view, spans)
            # Action-level OR does not encode alternatives inside an audience or
            # area list. Only consume an OR occurrence represented by a condition
            # or the supported relation between two positive directives.
            condition_spans = _condition_spans(view, pending)
            for connective in re.finditer(r"\bor\b", view, re.I):
                in_condition = any(a <= connective.start() and connective.end() <= b
                                   for a, b in condition_spans)
                between_actions = logic == LogicOperator.OR and any(
                    left[1] <= connective.start() and connective.end() <= right[0]
                    for left, right in zip(spans, spans[1:]))
                if pending and not in_condition and not between_actions:
                    unresolved.append(sentence.strip())
                    break
            sequential = _explicit_sequence(view, spans)
            positive_index = 0
            for item in pending:
                if not item.action.negated:
                    if logic == LogicOperator.OR:
                        item.action.logic_group = f"logic-sentence-{sentence_index}"
                        item.action.logic_operator = logic
                    if sequential:
                        item.action.sequence_group = f"sequence-sentence-{sentence_index}"
                        item.action.sequence_index = positive_index
                    positive_index += 1

            # Bind quantities/exceptions to the nearest operational directive in the same sentence.
            for q, qspan in zip(sentence_quantities, quantity_local_spans):
                if pending:
                    target = min(pending, key=lambda a: min(abs(qspan[0] - a.end), abs(qspan[1] - a.start)))
                    target.action.bound_quantities.append(q)

            exception_matches = list(re.finditer(r"\b(?:except(?:\s+for)?|unless)\s+([^.;]+)", view, re.I))
            for em in exception_matches:
                raw = sentence[em.start():em.end()]
                canonical = _canonical_exception(raw)
                start, end = sent_start + em.start(), sent_start + em.end()
                exceptions.append(ExceptionRule(text=canonical, evidence=_span(text, start, end)))
                if pending:
                    preceding = [a for a in pending if a.end <= em.start()]
                    target = max(preceding, key=lambda a: a.end) if preceding else min(pending, key=lambda a: abs(a.start - em.start()))
                    target.action.bound_exceptions.append(canonical)

            for item in pending:
                (prohibited if item.action.negated else required).append(item.action)

            clause = sentence.strip()
            residual_safety_cue = False
            residual_clause = clause
            if _has_unsupported_english_script_material(sentence):
                # The English extractor must not equate "recognized English action" with
                # "entire multilingual clause understood". Preserve the original clause
                # verbatim for review; do not translate or guess its semantics.
                residual_safety_cue = True
            elif _UNSUPPORTED_OPERATIONAL.search(view):
                residual_safety_cue = True
            elif _UNREPRESENTED_DEONTIC_CUE.search(view):
                residual_safety_cue = True
            elif _OPERATIONAL_CUE.search(view) and not pending:
                residual_safety_cue = True
            elif any((not item.action.negated and item.action.modality == Modality.UNKNOWN) for item in pending):
                residual_safety_cue = True
            elif _unsupported_event_identity(sentence, has_pending_action=bool(pending)):
                residual_safety_cue = True
            elif pending and _UNREPRESENTED_CONDITION_CUE.search(view):
                residual_safety_cue = True
            elif pending and (unbound_time := _unrepresented_temporal_occurrence(view, pending)):
                residual_safety_cue = True
                residual_clause = unbound_time
            elif restriction_clause := _unrepresented_restrictive_scope(sentence, pending):
                residual_safety_cue = True
                residual_clause = restriction_clause
            elif pending and _RELATIVE_TIME_CUE.search(view):
                # Relative calendar language is safety-relevant but not normalized
                # against a reference date by this deterministic extractor.
                residual_safety_cue = True
            elif pending and _has_unrepresented_severity_cue(sentence):
                residual_safety_cue = True
            elif pending and _has_unrepresented_certainty_cue(sentence):
                residual_safety_cue = True
            elif pending:
                unaccounted = _unaccounted_strong_subclause(sentence, pending)
                if not unaccounted:
                    unaccounted = _unaccounted_latin_residual(sentence, pending)
                if unaccounted:
                    residual_safety_cue = True
                    residual_clause = unaccounted
            elif (
                clause
                and not _confidently_non_operational_clause(sentence)
                and not _has_supported_non_action_semantics(sentence, sentence_quantities)
                and _substantive_latin_clause(sentence)
            ):
                # No directive or typed fact was extracted from a substantive Latin-script
                # sentence. We cannot establish that it is harmless English rather than
                # code-switched/unsupported operational meaning, so fail closed to REVIEW.
                residual_safety_cue = True

            if residual_safety_cue and residual_clause:
                unresolved.append(residual_clause)

        audience = _dedupe_text(_audiences(text) + [x for a in required + prohibited for x in a.scoped_audience])
        areas = _dedupe_text(_areas(text) + [x for a in required + prohibited for x in a.scoped_areas])
        hazard_name, hazard_span = self._hazard(text)
        hazard = Hazard(type=hazard_name, evidence=_span(text, *hazard_span)) if hazard_name and hazard_span else None

        severity_values, severity_uncertain = _severity_candidates(text)
        certainty_values, certainty_uncertain = _certainty_candidates(text)
        if len(severity_values) > 1:
            severity_uncertain.extend(
                m.group(0).strip() for m in _SENTENCE.finditer(text) if _SEVERITY_WORD.search(_lexical(m.group(0)))
            )
        if len(certainty_values) > 1:
            certainty_uncertain.extend(
                m.group(0).strip() for m in _SENTENCE.finditer(text) if _CERTAINTY_WORD.search(_lexical(m.group(0)))
            )
        unresolved.extend(x for x in severity_uncertain + certainty_uncertain if x)

        return SafetyContract(
            language=language,
            source_id=source_id,
            hazard=hazard,
            audience=audience,
            affected_areas=areas,
            required_actions=self._dedupe_actions(required),
            prohibited_actions=self._dedupe_actions(prohibited),
            urgency=_urgency(text),
            severity=_enum_or_unknown(severity_values, Severity.UNKNOWN),
            certainty=_enum_or_unknown(certainty_values, Certainty.UNKNOWN),
            quantities=self._dedupe_quantities(quantities),
            exceptions=self._dedupe_exceptions(exceptions),
            unresolved_operational_text=list(dict.fromkeys(unresolved)),
        )

    @staticmethod
    def _dedupe_actions(rows: list[Action]) -> list[Action]:
        out: list[Action] = []
        seen: set[tuple] = set()
        for row in rows:
            key = (
                row.type, row.verb.casefold(), (row.object or "").casefold(), (row.destination or "").casefold(),
                row.negated, row.modality, tuple(x.casefold() for x in row.scoped_audience),
                tuple(x.casefold() for x in row.scoped_areas), (row.condition or "").casefold(),
                tuple((x.operator.value, x.time.casefold()) for x in row.temporal_constraints),
                row.temporal_operator, (row.deadline or "").casefold(),
                tuple((q.value, q.unit.casefold(), q.relation.value, (q.meaning or "").casefold()) for q in row.bound_quantities),
                tuple(x.casefold() for x in row.bound_exceptions), row.sequence_group, row.sequence_index, row.logic_group, row.logic_operator,
            )
            if key not in seen:
                seen.add(key)
                out.append(row)
        return out

    @staticmethod
    def _dedupe_quantities(rows: list[Quantity]) -> list[Quantity]:
        out: list[Quantity] = []
        seen: set[tuple] = set()
        for row in rows:
            key = (row.value, row.unit.casefold(), row.relation.value, (row.meaning or "").casefold())
            if key not in seen:
                seen.add(key)
                out.append(row)
        return out

    @staticmethod
    def _dedupe_exceptions(rows: list[ExceptionRule]) -> list[ExceptionRule]:
        out: list[ExceptionRule] = []
        seen: set[str] = set()
        for row in rows:
            key = row.text.casefold()
            if key not in seen:
                seen.add(key)
                out.append(row)
        return out

    @staticmethod
    def _hazard(text: str) -> tuple[str | None, tuple[int, int] | None]:
        for name, pattern in _HAZARDS:
            match = re.search(pattern, _lexical(text), re.I)
            if match:
                return name, match.span()
        return None, None
