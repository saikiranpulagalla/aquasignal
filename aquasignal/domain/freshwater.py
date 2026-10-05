from __future__ import annotations

import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass

from signallock.contracts.normalization import normalize_time_string, normalize_unit
from signallock.contracts.schema import (
    Action,
    ActionType,
    EvidenceSpan,
    Modality,
    Quantity,
    QuantityRelation,
    SafetyContract,
    TemporalConstraint,
    TemporalOperator,
)


@dataclass(frozen=True, slots=True)
class FreshwaterProfile:
    """Declared, deliberately narrow deterministic language profile for AquaSignal V1."""

    profile_id: str = "freshwater-protective-communication-v1"
    language: str = "en"


@dataclass(frozen=True, slots=True)
class SourceReadiness:
    ready: bool
    reasons: tuple[str, ...]


_SENTENCE = re.compile(r".+?(?:[!?](?=\s|$)|(?<!\bSt)(?<!\bMt)\.(?=\s|$)|\n|$)", re.S | re.I)
_CLOCK = r"\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?|noon|midnight"
_TRAILING_TIME = re.compile(
    rf"^(?P<body>.*?)(?:\s+)(?P<op>until|before|after|at|starting(?:\s+at)?)\s+(?P<time>{_CLOCK})$",
    re.I,
)
_IMPRECISE_TIME = re.compile(
    r"^(?P<body>.*?)(?:\s+)(?P<op>until|before|after|at|starting(?:\s+at)?)\s+"
    r"(?P<time>this\s+(?:morning|afternoon|evening)|tonight|today|tomorrow|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|further\s+notice)$",
    re.I,
)
_BARE_RELATIVE_TIME = re.compile(
    r"^(?P<body>.*?)(?:\s+)(?P<time>this\s+(?:morning|afternoon|evening)|tonight|today|tomorrow)$",
    re.I,
)

_AUDIENCE_ALIASES = {
    "residents": "residents",
    "visitors": "visitors",
    "children": "children",
    "pet owners": "pet owners",
    "pets": "pets",
    "swimmers": "swimmers",
    "anglers": "anglers",
    "field staff": "field staff",
    "trained personnel": "trained personnel",
}
_AUDIENCE_ALT = "|".join(re.escape(x) for x in sorted(_AUDIENCE_ALIASES, key=len, reverse=True))
_DIRECT_VERB = r"enter|swim|wade|fish|drink"

_PLACE_NAME = r"[\w\u0300-\u036f][\w\u0300-\u036f .'\-]{0,120}"
_NAMED_AREA = re.compile(rf"^(?P<kind>stream|river|creek|site|zone)\s+(?P<name>{_PLACE_NAME})$", re.I | re.UNICODE)
_RELATIVE_AREA = re.compile(rf"^(?P<rel>upstream|downstream)\s+of\s+(?P<landmark>{_PLACE_NAME})$", re.I | re.UNICODE)
_NEAR_AREA = re.compile(rf"^near\s+(?P<landmark>{_PLACE_NAME})$", re.I | re.UNICODE)
_RESERVED_SCOPE_WORDS = {
    "until", "before", "after", "starting", "from", "to", "for", "next", "this", "morning", "afternoon", "evening", "today", "tonight", "tomorrow",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "utc", "gmt", "between",
    "bank", "banks", "near", "around", "within", "outside", "inside",
    "except", "unless", "if", "while", "only", "and", "or",
    "then", "also", "plus", "because", "when", "where", "but", "yet",
    "although", "though", "since", "therefore", "so", "due",
}

_DURATION = re.compile(
    r"(?P<prefix>at\s+least\s+)?(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>seconds?|secs?|minutes?|mins?|hours?|hrs?)",
    re.I,
)

_DURATION_SCALE = {
    "s": Decimal("1"),
    "min": Decimal("60"),
    "h": Decimal("3600"),
}


def aqua_exact_duration_seconds(quantity: Quantity) -> Decimal | None:
    """Return an exact Decimal duration for Aqua boil evidence when represented.

    SafetyContract retains float values for inherited compatibility, but AquaSignal's
    deterministic extractor also preserves the original numeric evidence. Using that
    evidence here prevents both float-precision collisions and arbitrary rounding from
    changing deduplication/conflict semantics.
    """
    if (quantity.meaning or "").casefold() != "boil duration":
        return None
    evidence = getattr(quantity, "evidence", None)
    quote = getattr(evidence, "quote", None) if evidence is not None else None
    if not quote:
        return None
    match = _DURATION.fullmatch(quote.strip())
    if not match:
        return None
    scale = _DURATION_SCALE.get(normalize_unit(match.group("unit")))
    if scale is None:
        return None
    try:
        return Decimal(match.group("value")) * scale
    except InvalidOperation:
        return None

_CONTACT = re.compile(
    rf"^(?:(?P<audience>{_AUDIENCE_ALT})\s+)?(?:(?P<force>must|should|may|can)\s+)?"
    r"avoid\s+(?P<direct>direct\s+)?contact(?:\s+with)?(?:\s+(?P<scope>.+))?$",
    re.I,
)
_TOUCH = re.compile(
    rf"^(?:(?P<audience>{_AUDIENCE_ALT})\s+)?(?P<force>do\s+not|don't|never|must\s+not|should\s+not)\s+"
    r"touch(?:\s+(?:the\s+)?water)?(?:\s+(?:in|from)\s+(?P<scope>.+))?$",
    re.I,
)
_DIRECT_PROHIBITION = re.compile(
    rf"^(?:(?P<audience>{_AUDIENCE_ALT})\s+)?(?P<force>do\s+not|don't|never|must\s+not|should\s+not)\s+"
    rf"(?P<v1>{_DIRECT_VERB})(?:\s+or\s+(?P<v2>{_DIRECT_VERB}))?"
    r"(?:\s+(?:the\s+)?water)?(?:\s+(?:in|from)\s+|\s+)(?P<scope>.+)$",
    re.I,
)
_DIRECT_PROHIBITION_NO_SCOPE = re.compile(
    rf"^(?:(?P<audience>{_AUDIENCE_ALT})\s+)?(?P<force>do\s+not|don't|never|must\s+not|should\s+not)\s+"
    rf"(?P<v1>{_DIRECT_VERB})(?:\s+or\s+(?P<v2>{_DIRECT_VERB}))?(?:\s+(?:the\s+)?water)?$",
    re.I,
)
_POSITIVE_COUNTERDIRECTIVE = re.compile(
    rf"^(?:(?P<audience>{_AUDIENCE_ALT})\s+)?(?:(?P<force>must|may|can|should)\s+)?(?P<verb>{_DIRECT_VERB})"
    r"(?:\s+(?:the\s+)?water)?(?:\s+(?:in|from)\s+|\s+)(?P<scope>.+)$",
    re.I,
)
_POSITIVE_CONTACT = re.compile(
    rf"^(?:(?P<audience>{_AUDIENCE_ALT})\s+)?(?:(?P<force>must|may|can|should)\s+)?"
    r"(?P<verb>touch|contact)(?:\s+(?:the\s+)?water)?(?:\s+(?:in|from)\s+|\s+)(?P<scope>.+)$",
    re.I,
)
_NEGATED_AVOID = re.compile(
    rf"^(?:(?P<audience>{_AUDIENCE_ALT})\s+)?(?P<force>do\s+not|don\'t|never|must\s+not|should\s+not)\s+"
    r"avoid\s+(?P<direct>direct\s+)?contact(?:\s+with)?(?:\s+(?P<scope>.+))?$",
    re.I,
)
_KEEP_AWAY = re.compile(r"^keep\s+(?P<audiences>.+?)\s+away\s+from\s+(?P<scope>.+)$", re.I)
_BOIL = re.compile(
    r"^boil\s+(?:the\s+)?water\s+for\s+(?P<duration>.+?)\s+before\s+drinking$",
    re.I,
)
_COLLECT = re.compile(
    r"^(?P<only>only\s+)?(?P<audience>trained\s+personnel|field\s+staff)\s+may\s+collect\s+samples?\s+from\s+(?P<scope>.+)$",
    re.I,
)


# Same-width typographic normalization keeps evidence character offsets valid while
# accepting punctuation substitutions commonly produced by text editors/LLMs.
_SYNTAX_TRANSLATION = str.maketrans({
    "\u2018": "'", "\u2019": "'",
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u00a0": " ", "\u202f": " ",
})


def _syntax_normalize_same_width(value: str) -> str:
    return value.translate(_SYNTAX_TRANSLATION)


_IDENTIFIER_PUNCT_TRANSLATION = str.maketrans({
    "\u2018": "'", "\u2019": "'",
    "\u2010": "-", "\u2011": "-", "\u2012": "-",
    "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u00a0": " ", "\u202f": " ",
})


def aqua_identifier_text_key(value: str | None) -> str:
    """Normalize identifier typography without compatibility-folding identity.

    Operational identifiers are case-insensitive for ordinary Unicode letters and
    canonically equivalent sequences, but compatibility characters (for example
    ``①``, full-width ``Ａ``, ``Ⅳ``, ``ﬁ`` or Greek symbol ``ϴ``) remain distinct
    from the ordinary characters they resemble.  This prevents NFKC/case-mapping
    collisions while retaining normal ``A``/``a`` and ``É``/``é`` equivalence.
    """
    if not value:
        return ""
    text = unicodedata.normalize("NFC", value.translate(_IDENTIFIER_PUNCT_TRANSLATION))
    normalized: list[str] = []
    for ch in text:
        # A compatibility character must retain its exact identity.  Ordinary
        # characters may be lower-cased so normal case-only differences stay clean.
        if unicodedata.normalize("NFKC", ch) != ch:
            normalized.append(ch)
        else:
            normalized.append(ch.lower())
    return " ".join("".join(normalized).strip().split())


def aqua_canonical_place(value: str | None) -> str:
    """Canonicalize a freshwater place label while preserving identifier tokens."""
    text = aqua_identifier_text_key(value)
    if not text:
        return ""
    # An internal period is retained because it can be part of a site identifier
    # (``Site A.B`` must not collapse to ``Site A B``).
    text = re.sub(r"[^\w\s.'\-]", " ", text)
    return " ".join(text.split())


def _evidence(text: str, start: int, end: int) -> EvidenceSpan:
    return EvidenceSpan(quote=text[start:end].strip(), start_char=start, end_char=end)


def _prohibition_force_tag(force: str | None, *, avoid_imperative: bool = False) -> str:
    value = " ".join((force or "").casefold().split())
    if value == "should" or value == "should not":
        return "aqua-force:advisory-prohibition"
    if avoid_imperative or value in {"", "must", "do not", "don't", "never", "must not"}:
        return "aqua-force:strong-prohibition"
    return "aqua-force:unknown-prohibition"


def _contact_constraint_tags(*, force: str | None, direct: bool, avoid_imperative: bool = False) -> list[str]:
    # In the declared V1 freshwater profile, "contact", "direct contact", and
    # "touch water" are treated as the same physical-contact prohibition.  The
    # lexical modifier is therefore intentionally not a separate invariant.
    return [_prohibition_force_tag(force, avoid_imperative=avoid_imperative)]


def _valid_clock_token(value: str) -> bool:
    raw = " ".join(value.casefold().replace(".", "").split())
    if raw in {"noon", "midnight"}:
        return True
    ampm = re.fullmatch(r"(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<p>am|pm)", raw)
    if ampm:
        hour = int(ampm.group("h")); minute = int(ampm.group("m") or 0)
        return 1 <= hour <= 12 and 0 <= minute <= 59
    twenty_four = re.fullmatch(r"(?P<h>\d{1,2}):(?P<m>\d{2})", raw)
    if twenty_four:
        return 0 <= int(twenty_four.group("h")) <= 23 and 0 <= int(twenty_four.group("m")) <= 59
    return False


def _split_temporal(core: str) -> tuple[str, list[TemporalConstraint]]:
    stripped = core.strip()
    match = _TRAILING_TIME.fullmatch(stripped)
    if not match:
        imprecise = _IMPRECISE_TIME.fullmatch(stripped) or _BARE_RELATIVE_TIME.fullmatch(stripped)
        if imprecise:
            body = imprecise.group("body").strip()
            if body.endswith(","):
                body = body[:-1].rstrip()
            return body, [
                TemporalConstraint(operator=TemporalOperator.UNKNOWN, time=imprecise.group("time").strip())
            ]
        return stripped, []
    if not _valid_clock_token(match.group("time")):
        return stripped, []
    mapping = {
        "until": TemporalOperator.UNTIL,
        "before": TemporalOperator.BEFORE,
        "after": TemporalOperator.AFTER,
        "at": TemporalOperator.AT,
        "starting": TemporalOperator.STARTING,
        "starting at": TemporalOperator.STARTING,
    }
    op = " ".join(match.group("op").casefold().split())
    body = match.group("body").strip()
    if body.endswith(","):
        body = body[:-1].rstrip()
    return body, [TemporalConstraint(operator=mapping[op], time=match.group("time").strip())]


def _parse_audience_prefix(value: str | None) -> list[str]:
    if not value:
        return []
    key = " ".join(value.casefold().split())
    result = _AUDIENCE_ALIASES.get(key)
    return [result] if result else []


def _parse_keep_audiences(value: str) -> list[str] | None:
    # V1 supports a deliberately narrow conjunction of declared audience terms.
    parts = [" ".join(x.casefold().split()) for x in re.split(r"\s+and\s+", value.strip(), flags=re.I)]
    if not parts or len(parts) > 2:
        return None
    parsed: list[str] = []
    for part in parts:
        audience = _AUDIENCE_ALIASES.get(part)
        if not audience:
            return None
        parsed.append(audience)
    return list(dict.fromkeys(parsed))


def _scope_has_reserved_semantics(value: str) -> bool:
    tokens = set(re.findall(r"[a-z]+", value.casefold()))
    return bool(tokens & _RESERVED_SCOPE_WORDS)


def _parse_scope(value: str | None) -> list[str] | None:
    if value is None:
        return []
    scope = " ".join(value.strip().split())
    if not scope:
        return []
    low = scope.casefold()
    # "stream water" is the medium, not a named site. It may precede a supported
    # relative location (e.g. stream water downstream of Bridge A).
    if low == "stream water" or low == "water":
        return []
    for prefix in ("the water in ", "stream water in ", "water in ", "stream water ", "water "):
        if low.startswith(prefix):
            scope = scope[len(prefix):].strip()
            low = scope.casefold()
            break
    near = _NEAR_AREA.fullmatch(scope)
    if near:
        landmark = " ".join(near.group("landmark").split())
        return [f"near {landmark}"]
    if _scope_has_reserved_semantics(scope):
        return None
    relative = _RELATIVE_AREA.fullmatch(scope)
    if relative:
        landmark = " ".join(relative.group("landmark").split())
        return [f"{relative.group('rel').casefold()} of {landmark}"]
    named = _NAMED_AREA.fullmatch(scope)
    if named:
        name = " ".join(named.group("name").split())
        if name.casefold() in {"water", "waters", "bed", "bank", "banks"}:
            return None
        return [f"{named.group('kind').casefold()} {name}"]
    return None


def _action(
    *,
    action_type: ActionType,
    verb: str,
    obj: str | None,
    sentence: str,
    sentence_start: int,
    prohibited: bool,
    audiences: list[str] | None = None,
    areas: list[str] | None = None,
    times: list[TemporalConstraint] | None = None,
    condition: str | None = None,
    quantities: list[Quantity] | None = None,
    exceptions: list[str] | None = None,
) -> Action:
    modality = Modality.PROHIBITED if prohibited else Modality.MUST
    return Action(
        type=action_type,
        verb=verb,
        object=obj,
        negated=prohibited,
        evidence=EvidenceSpan(
            quote=sentence.strip(),
            start_char=sentence_start,
            end_char=sentence_start + len(sentence),
        ),
        modality=modality,
        scoped_audience=audiences or [],
        scoped_areas=areas or [],
        condition=condition,
        temporal_constraints=times or [],
        bound_quantities=quantities or [],
        bound_exceptions=exceptions or [],
    )


def _quantity_semantic_key(quantity: Quantity) -> tuple:
    meaning = " ".join((quantity.meaning or "").casefold().split())
    exact_seconds = aqua_exact_duration_seconds(quantity)
    if exact_seconds is not None:
        magnitude = ("exact-seconds", exact_seconds)
    else:
        value = float(quantity.value)
        magnitude = (
            normalize_unit(quantity.unit),
            Decimal(str(value)) if math.isfinite(value) else repr(value),
        )
    return (
        magnitude,
        quantity.relation.value,
        meaning,
    )


def _action_identity_key(action: Action) -> tuple:
    """Core directive identity excluding force/time/quantity modifiers."""
    return (
        action.type.value,
        action.verb.casefold().strip(),
        (action.object or "").casefold().strip(),
        tuple(sorted(" ".join(x.casefold().split()) for x in action.scoped_audience)),
        tuple(sorted(aqua_canonical_place(x) for x in action.scoped_areas)),
    )


def _action_semantic_key(action: Action) -> tuple:
    """Evidence-free semantic identity used only to collapse exact duplicate directives.

    This intentionally does not merge merely similar actions. Every operational slot
    that the verifier compares remains part of the key, so deduplication cannot hide
    an audience/place/time/quantity/constraint difference.
    """
    return (
        action.type.value,
        action.verb.casefold().strip(),
        (action.object or "").casefold().strip(),
        (action.destination or "").casefold().strip(),
        (action.condition or "").casefold().strip(),
        bool(action.negated),
        action.modality.value,
        tuple(sorted(" ".join(x.casefold().split()) for x in action.scoped_audience)),
        tuple(sorted(aqua_canonical_place(x) for x in action.scoped_areas)),
        tuple((x.operator.value, normalize_time_string(x.time)) for x in action.temporal_constraints),
        tuple(sorted(_quantity_semantic_key(x) for x in action.bound_quantities)),
        tuple(sorted(" ".join(x.casefold().split()) for x in action.bound_exceptions)),
        action.sequence_group,
        action.sequence_index,
        action.logic_group,
        action.logic_operator.value,
    )


def _dedupe_actions(actions: list[Action]) -> list[Action]:
    out: list[Action] = []
    seen: set[tuple] = set()
    for action in actions:
        key = _action_semantic_key(action)
        if key in seen:
            continue
        seen.add(key)
        out.append(action)
    return out


def _dedupe_quantities(quantities: list[Quantity]) -> list[Quantity]:
    out: list[Quantity] = []
    seen: set[tuple] = set()
    for quantity in quantities:
        key = _quantity_semantic_key(quantity)
        if key in seen:
            continue
        seen.add(key)
        out.append(quantity)
    return out


def _strip_line_list_markers_same_width(text: str) -> str:
    """Normalize line-leading list decoration without changing text width.

    A marked line is an explicit directive boundary even when the previous item has
    no terminal punctuation.  We therefore blank only the marker/indentation and,
    for every *subsequent* marked line, turn the immediately preceding newline into
    a synthetic period **only when the previous non-whitespace character is not
    already sentence punctuation**.  This preserves one-to-one character offsets,
    keeps ordinary visual line-wraps joinable, and prevents two bullet directives
    from being merged into one partially understood sentence.

    Inline dashes/numbers remain untouched.
    """
    chars = list(text)
    marker_re = re.compile(r"(?m)^[ \t]*(?:[-*•]|\d{1,3}[.)])[ \t]+")
    for match in marker_re.finditer(text):
        # A list marker after a physical newline is an explicit item boundary.
        line_start = match.start()
        if line_start > 0 and text[line_start - 1] == "\n":
            previous = line_start - 2
            if previous >= 0 and text[previous] == "\r":
                previous -= 1
            while previous >= 0 and text[previous] in {" ", "\t"}:
                previous -= 1
            if previous >= 0 and text[previous] not in ".!?":
                chars[line_start - 1] = "."
        for index in range(match.start(), match.end()):
            if chars[index] not in {"\r", "\n"}:
                chars[index] = " "
    return "".join(chars)


class FreshwaterExtractor:
    """Fail-closed deterministic English extractor for the AquaSignal V1 profile.

    Automatic PASS requires *complete sentence qualification*. A partially understood
    sentence is not considered represented merely because one keyword matched.
    """

    profile = FreshwaterProfile()

    def extract(self, text: str, *, source_id: str | None = None) -> SafetyContract:
        required: list[Action] = []
        prohibited: list[Action] = []
        global_audience: list[str] = []
        global_areas: list[str] = []
        quantities: list[Quantity] = []
        unresolved: list[str] = []

        # Physical line wrapping is presentation, not operational semantics.  Scan a
        # same-width view where CR/LF are spaces so copied PDF/email/SMS wraps do not
        # split one directive into unrelated fragments.  Sentence punctuation still
        # separates directives, and using a same-width view preserves exact evidence
        # offsets back into the original text.
        scan_text = _strip_line_list_markers_same_width(text).translate(
            {ord("\r"): " ", ord("\n"): " "}
        )

        for sentence_match in _SENTENCE.finditer(scan_text):
            raw_scan = sentence_match.group(0)
            left_trim = len(raw_scan) - len(raw_scan.lstrip())
            right_trim = len(raw_scan) - len(raw_scan.rstrip())
            start = sentence_match.start() + left_trim
            end = sentence_match.end() - right_trim
            # A synthetic period inserted at a list-item newline is only a scan-view
            # boundary.  Exclude the original CR/LF from the evidence span so quote,
            # start_char and end_char remain exact coordinates into the authoritative
            # input rather than coordinates that include presentation-only line breaks.
            if end > start and scan_text[end - 1] == "." and text[end - 1] == "\n":
                end -= 1
                if end > start and text[end - 1] == "\r":
                    end -= 1
            sentence = text[start:end]
            if not sentence:
                continue
            syntax_sentence = _syntax_normalize_same_width(raw_scan.strip())
            core = syntax_sentence.rstrip(".!?;,: ").strip()
            body, times = _split_temporal(core)
            parsed = False

            # Explicit polarity reversal: model a candidate-side positive action so
            # the comparator can decisively BLOCK it, while still marking the clause
            # unresolved so the same sentence can never become authoritative source.
            match = _NEGATED_AVOID.fullmatch(body)
            if match:
                audiences = _parse_audience_prefix(match.group("audience"))
                areas = _parse_scope(match.group("scope"))
                if areas is not None:
                    required.append(_action(
                        action_type=ActionType.EXECUTE, verb="contact", obj="water",
                        sentence=sentence, sentence_start=start, prohibited=False,
                        audiences=audiences, areas=areas, times=times,
                        exceptions=["aqua-source-unsupported:positive-counterdirective"],
                    ))
                    global_audience.extend(audiences)
                    global_areas.extend(areas)
                unresolved.append(sentence)
                continue

            match = _CONTACT.fullmatch(body)
            if match:
                audiences = _parse_audience_prefix(match.group("audience"))
                force = (match.group("force") or "").casefold()
                # An unmodalized third-person statement ("Visitors avoid …") can be
                # descriptive rather than directive. V1 only treats bare "Avoid …"
                # as an imperative; an explicit audience requires must/should.
                if match.group("audience") and not match.group("force"):
                    areas = None
                else:
                    areas = _parse_scope(match.group("scope"))
                if areas is not None:
                    prohibited.append(_action(
                        action_type=ActionType.AVOID, verb="contact", obj="water",
                        sentence=sentence, sentence_start=start, prohibited=True,
                        audiences=audiences, areas=areas, times=times,
                        exceptions=_contact_constraint_tags(force=force, direct=bool(match.group("direct")), avoid_imperative=not force),
                    ))
                    global_audience.extend(audiences)
                    global_areas.extend(areas)
                    parsed = True
                    if force in {"may", "can"} or (audiences and not force):
                        # Parse candidate wording so any independently provable
                        # force change remains visible, but never allow permissive
                        # or audience-led bare declaratives to become authoritative
                        # source language.
                        unresolved.append(sentence)

            if not parsed:
                match = _TOUCH.fullmatch(body)
                if match:
                    audiences = _parse_audience_prefix(match.group("audience"))
                    areas = _parse_scope(match.group("scope"))
                    if areas is not None:
                        prohibited.append(_action(
                            action_type=ActionType.AVOID, verb="contact", obj="water",
                            sentence=sentence, sentence_start=start, prohibited=True,
                            audiences=audiences, areas=areas, times=times,
                            exceptions=_contact_constraint_tags(force=match.group("force"), direct=True),
                        ))
                        global_audience.extend(audiences)
                        global_areas.extend(areas)
                        parsed = True

            if not parsed:
                match = _DIRECT_PROHIBITION.fullmatch(body) or _DIRECT_PROHIBITION_NO_SCOPE.fullmatch(body)
                if match:
                    audiences = _parse_audience_prefix(match.group("audience"))
                    areas = _parse_scope(match.groupdict().get("scope"))
                    if areas is not None:
                        verbs = [match.group("v1")]
                        if match.group("v2"):
                            verbs.append(match.group("v2"))
                        for verb in verbs:
                            prohibited.append(_action(
                                action_type=ActionType.AVOID,
                                verb=verb.casefold(),
                                obj="fish" if verb.casefold() == "fish" else "water",
                                sentence=sentence,
                                sentence_start=start,
                                prohibited=True,
                                audiences=audiences,
                                areas=areas,
                                times=times,
                                exceptions=[_prohibition_force_tag(match.group("force"))],
                            ))
                        global_audience.extend(audiences)
                        global_areas.extend(areas)
                        parsed = True

            if not parsed:
                match = _KEEP_AWAY.fullmatch(body)
                if match:
                    audiences = _parse_keep_audiences(match.group("audiences"))
                    areas = _parse_scope(match.group("scope"))
                    if audiences is not None and areas is not None:
                        required.append(_action(
                            action_type=ActionType.AVOID, verb="keep away", obj="water",
                            sentence=sentence, sentence_start=start, prohibited=False,
                            audiences=audiences, areas=areas, times=times,
                        ))
                        global_audience.extend(audiences)
                        global_areas.extend(areas)
                        parsed = True

            # Boil guidance has its own duration and "before drinking" grammar;
            # generic clock-time parsing is intentionally not used here.
            if not parsed and not times:
                match = _BOIL.fullmatch(body)
                if match:
                    duration = _DURATION.fullmatch(match.group("duration").strip())
                    if duration:
                        numeric_value = float(duration.group("value"))
                        if math.isfinite(numeric_value):
                            relation = QuantityRelation.GREATER_OR_EQUAL if duration.group("prefix") else QuantityRelation.EQUAL
                            unit = duration.group("unit")
                            # Evidence is sentence-level here; the semantic quantity is
                            # still typed and independently compared.
                            duration_start = start + match.start("duration")
                            duration_end = duration_start + len(match.group("duration"))
                            q = Quantity(
                                value=numeric_value, unit=unit, relation=relation,
                                meaning="boil duration", evidence=EvidenceSpan(
                                    quote=duration.group(0), start_char=duration_start, end_char=duration_end
                                ),
                            )
                            required.append(_action(
                                action_type=ActionType.EXECUTE, verb="boil", obj="water",
                                sentence=sentence, sentence_start=start, prohibited=False,
                                condition="before drinking", quantities=[q],
                            ))
                            quantities.append(q)
                            parsed = True

            if not parsed and not times:
                match = _COLLECT.fullmatch(body)
                if match:
                    areas = _parse_scope(match.group("scope"))
                    if areas is not None:
                        audience = " ".join(match.group("audience").casefold().split())
                        exceptions = [f"only:{audience}"] if match.group("only") else []
                        required.append(_action(
                            action_type=ActionType.OTHER, verb="collect", obj="samples",
                            sentence=sentence, sentence_start=start, prohibited=False,
                            audiences=[audience], areas=areas, exceptions=exceptions,
                        ))
                        global_audience.append(audience)
                        global_areas.extend(areas)
                        parsed = True

            # Positive risk actions are useful candidate evidence because they are a
            # decisive polarity reversal against a source prohibition. They remain
            # outside the authoritative-source profile and therefore are unresolved.
            if not parsed:
                match = _POSITIVE_CONTACT.fullmatch(body)
                if match:
                    audiences = _parse_audience_prefix(match.group("audience"))
                    areas = _parse_scope(match.group("scope"))
                    if areas is not None:
                        required.append(_action(
                            action_type=ActionType.EXECUTE, verb="contact", obj="water",
                            sentence=sentence, sentence_start=start, prohibited=False,
                            audiences=audiences, areas=areas, times=times,
                            exceptions=["aqua-source-unsupported:positive-counterdirective"],
                        ))
                        global_audience.extend(audiences)
                        global_areas.extend(areas)
                    unresolved.append(sentence)
                    continue

            if not parsed:
                match = _POSITIVE_COUNTERDIRECTIVE.fullmatch(body)
                if match:
                    audiences = _parse_audience_prefix(match.group("audience"))
                    areas = _parse_scope(match.group("scope"))
                    if areas is not None:
                        verb = match.group("verb").casefold()
                        required.append(_action(
                            action_type=ActionType.EXECUTE, verb=verb,
                            obj="fish" if verb == "fish" else "water",
                            sentence=sentence, sentence_start=start, prohibited=False,
                            audiences=audiences, areas=areas, times=times,
                            exceptions=["aqua-source-unsupported:positive-counterdirective"],
                        ))
                        global_audience.extend(audiences)
                        global_areas.extend(areas)
                    unresolved.append(sentence)
                    continue

            if parsed and any(t.operator == TemporalOperator.UNKNOWN for t in times):
                # Preserve structured candidate evidence for known imprecision while
                # still marking the clause outside the authoritative-source profile.
                unresolved.append(sentence)

            if not parsed:
                # No free-form metadata exception exists inside a protective advisory.
                # Unknown sentences are evidence, never silent whitespace.
                unresolved.append(sentence)

        return SafetyContract(
            language="en",
            audience=list(dict.fromkeys(global_audience)),
            affected_areas=list(dict.fromkeys(global_areas)),
            required_actions=_dedupe_actions(required),
            prohibited_actions=_dedupe_actions(prohibited),
            quantities=_dedupe_quantities(quantities),
            unresolved_operational_text=list(dict.fromkeys(unresolved)),
            source_id=source_id,
        )


def assess_source_readiness(contract: SafetyContract) -> SourceReadiness:
    reasons: list[str] = []
    if contract.language.split("-")[0].casefold() != "en":
        reasons.append("Freshwater Protective Communication Profile v1 is qualified only for English.")
    if not (contract.required_actions or contract.prohibited_actions):
        reasons.append("No supported protective action was extracted from the authoritative advisory.")
    if contract.unresolved_operational_text:
        reasons.append("Authoritative advisory contains unresolved operational meaning.")
    actions = contract.required_actions + contract.prohibited_actions
    if any(
        any(x.startswith("aqua-source-unsupported:") for x in action.bound_exceptions)
        for action in actions
    ):
        reasons.append("Authoritative advisory contains a directive outside the supported source profile.")
    if any(
        temporal.operator == TemporalOperator.UNKNOWN
        for action in actions
        for temporal in action.temporal_constraints
    ):
        reasons.append("Authoritative advisory contains an imprecise or unsupported temporal expression.")
    bound_quantities = [quantity for action in actions for quantity in action.bound_quantities]
    if any(not math.isfinite(float(quantity.value)) for quantity in bound_quantities):
        reasons.append("Authoritative advisory contains a non-finite protective quantity.")
    if any(math.isfinite(float(quantity.value)) and float(quantity.value) <= 0 for quantity in bound_quantities):
        reasons.append("Authoritative advisory contains a non-positive protective quantity.")
    if any(
        aqua_canonical_place(area).startswith("near ")
        for action in actions
        for area in action.scoped_areas
    ):
        reasons.append("Authoritative advisory contains an imprecise freshwater location relation.")
    by_identity: dict[tuple, set[tuple]] = {}
    for action in actions:
        by_identity.setdefault(_action_identity_key(action), set()).add(_action_semantic_key(action))
    if any(len(variants) > 1 for variants in by_identity.values()):
        reasons.append("Authoritative advisory contains conflicting constraints for the same protective directive.")

    return SourceReadiness(ready=not reasons, reasons=tuple(dict.fromkeys(reasons)))
