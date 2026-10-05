from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AquaContextSource(StrEnum):
    RESILIENCE_COMPATIBLE_CSV = "resilience-map-compatible-csv"
    ENVIRONMENTAL_FHIR_JSON = "environmental-fhir-json"
    SYNTHETIC = "synthetic"


class AquaContext(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source: AquaContextSource
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    site: str | None = Field(default=None, max_length=200)
    date_range: str | None = Field(default=None, max_length=200)
    indicators: list[str] = Field(default_factory=list, max_length=50)
    resource_type: str | None = Field(default=None, max_length=80)
    profile: str | None = Field(default=None, max_length=500)
    resource_id: str | None = Field(default=None, max_length=200)
    synthetic_demo: bool = False
    raw_summary: dict[str, Any] = Field(default_factory=dict)

    @field_validator("indicators")
    @classmethod
    def _bound_indicators(cls, values: list[str]) -> list[str]:
        if any(len(value) > 250 for value in values):
            raise ValueError("context indicators must be at most 250 characters each")
        return values

    @field_validator("raw_summary")
    @classmethod
    def _bound_raw_summary(cls, value: dict[str, Any]) -> dict[str, Any]:
        # Context is supplied back by the client before HMAC verification.  Bound its
        # structure first so a forged deeply nested object cannot crash canonical JSON
        # hashing before the invalid token is rejected.
        stack: list[tuple[Any, int]] = [(value, 1)]
        nodes = 0
        while stack:
            item, depth = stack.pop()
            nodes += 1
            if nodes > 2_000:
                raise ValueError("context raw_summary exceeds the 2,000-node prototype limit")
            if depth > 12:
                raise ValueError("context raw_summary exceeds the maximum nesting depth of 12")
            if isinstance(item, dict):
                for key, child in item.items():
                    if not isinstance(key, str) or len(key) > 250:
                        raise ValueError("context raw_summary keys must be strings up to 250 characters")
                    stack.append((child, depth + 1))
            elif isinstance(item, list):
                if len(item) > 500:
                    raise ValueError("context raw_summary lists exceed the 500-item prototype limit")
                for child in item:
                    stack.append((child, depth + 1))
            elif isinstance(item, str) and len(item) > 1_000:
                raise ValueError("context raw_summary strings must be at most 1,000 characters")
            elif isinstance(item, float) and not math.isfinite(item):
                raise ValueError("context raw_summary cannot contain NaN or Infinity")
        return value


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def context_blob(context: AquaContext) -> str:
    return json.dumps(context.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _reject_unsafe_unicode(value: str, *, label: str) -> str:
    """Reject invisible/control metadata that can spoof provenance displays."""
    for ch in value:
        if unicodedata.category(ch).startswith("C"):
            raise ValueError(f"{label} contains unsupported control/format Unicode characters")
    return value


def _field_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    return " ".join(value.casefold().replace("_", " ").replace("-", " ").split())


def _display_key(value: str) -> str:
    # Keep context-site identity exactly aligned with advisory-site identity.
    # Column *headers* remain prose-like aliases and intentionally use NFKC above.
    from aquasignal.domain.freshwater import aqua_identifier_text_key

    return aqua_identifier_text_key(value)


def _parse_iso_datetime(value: str) -> datetime:
    raw = value.strip()
    if not raw:
        raise ValueError("CSV date/time values cannot be blank")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"CSV date/time value is not ISO-8601 compatible: {raw!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        return dt.astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise ValueError(
            f"CSV date/time value falls outside the representable UTC range: {raw!r}"
        ) from exc


def _sort_date_values(values: list[str]) -> list[str]:
    # Sorting aware UTC datetimes avoids platform-dependent timestamp() conversion
    # while preserving the original text for provenance display.
    return sorted(values, key=_parse_iso_datetime)


def _temporal_alias_value(value: str) -> tuple[str, object, datetime | None]:
    """Parse a populated date/datetime alias for cross-column consistency checks.

    Date-only columns are intentionally compatible with a timestamp on the same
    local calendar date; two full timestamps must identify the same instant.  This
    catches contradictory duplicate provenance columns without breaking common
    exports that carry both a coarse ``date`` and a precise ``timestamp``.
    """
    raw = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            local = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError(f"CSV date/time value is not ISO-8601 compatible: {raw!r}") from exc
        return "date", local.date(), None

    try:
        local = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"CSV date/time value is not ISO-8601 compatible: {raw!r}") from exc
    if local.tzinfo is None:
        local = local.replace(tzinfo=timezone.utc)
    try:
        utc = local.astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise ValueError(
            f"CSV date/time value falls outside the representable UTC range: {raw!r}"
        ) from exc
    return "datetime", local.date(), utc


def _temporal_aliases_compatible(left: tuple[str, object, datetime | None], right: tuple[str, object, datetime | None]) -> bool:
    lkind, ldate, lutc = left
    rkind, rdate, rutc = right
    if lkind == "date" or rkind == "date":
        return ldate == rdate
    return lutc == rutc


def parse_resilience_csv(data: bytes, *, synthetic_demo: bool = False) -> AquaContext:
    if len(data) > 2_000_000:
        raise ValueError("CSV context exceeds the 2 MB prototype limit")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV context must be UTF-8 text") from exc
    reader = csv.DictReader(io.StringIO(text))
    try:
        fieldnames = reader.fieldnames
    except csv.Error as exc:
        raise ValueError(f"CSV parsing failed: {exc}") from exc
    if not fieldnames:
        raise ValueError("CSV must contain a header row")
    raw_fields = [str(x).strip() if x is not None else "" for x in fieldnames]
    for field in raw_fields:
        _reject_unsafe_unicode(field, label="CSV header")
    if any(not x for x in raw_fields):
        raise ValueError("CSV header names cannot be blank")
    if len(raw_fields) > 200:
        raise ValueError("CSV context exceeds the 200-column prototype limit")
    if any(len(x) > 250 for x in raw_fields):
        raise ValueError("CSV header names must be at most 250 characters")
    normalized_fields = [_field_key(x) for x in raw_fields]
    if len(set(normalized_fields)) != len(normalized_fields):
        raise ValueError("CSV contains ambiguous duplicate header names")
    try:
        rows = list(reader)
    except csv.Error as exc:
        raise ValueError(f"CSV parsing failed: {exc}") from exc
    if not rows:
        raise ValueError("CSV context must contain at least one data row")
    if len(rows) > 20_000:
        raise ValueError("CSV context exceeds the 20,000-row prototype limit")
    if any(None in row and any(str(x).strip() for x in (row.get(None) or [])) for row in rows):
        raise ValueError("CSV row contains more values than declared headers")
    fields = raw_fields

    # Alias selection is priority-driven rather than header-order-driven so the
    # same export semantics do not change merely because columns were rearranged.
    site_aliases = ("site", "site name", "station", "station name", "location", "location name")
    date_aliases = ("datetime", "timestamp", "observed at", "observation date", "date", "time")

    def find_field(aliases: tuple[str, ...]) -> str | None:
        keyed = {_field_key(field): field for field in fields}
        # Header presence alone is not enough: exports can retain a preferred alias
        # column while leaving it blank and populating a lower-priority alias. Pick
        # the highest-priority alias that actually carries data.
        for alias in aliases:
            field = keyed.get(alias)
            if field and any((row.get(field) or "").strip() for row in rows):
                return field
        return next((keyed[alias] for alias in aliases if alias in keyed), None)

    def distinct_values(
        field: str | None,
        *,
        limit: int = 200,
        canonicalize: bool = False,
        label: str = "CSV metadata",
    ) -> list[str]:
        if not field:
            return []
        values: list[str] = []
        seen: set[str] = set()
        for row in rows:
            value = " ".join((row.get(field) or "").strip().split())
            if not value:
                continue
            _reject_unsafe_unicode(value, label=label)
            key = _display_key(value) if canonicalize else value
            if key in seen:
                continue
            seen.add(key)
            values.append(value)
            if len(values) >= limit:
                break
        return values

    site_field = find_field(site_aliases)
    date_field = find_field(date_aliases)
    keyed_fields = {_field_key(field): field for field in fields}
    site_fields = [keyed_fields[alias] for alias in site_aliases if alias in keyed_fields]
    date_fields = [keyed_fields[alias] for alias in date_aliases if alias in keyed_fields]

    # Multiple populated date/datetime aliases must not silently disagree.  A
    # separate ``time`` column is intentionally excluded because it commonly
    # complements a date column rather than duplicating it.
    comparable_date_fields = [field for field in date_fields if _field_key(field) != "time"]
    if len(comparable_date_fields) > 1:
        for row in rows:
            parsed_aliases: list[tuple[str, tuple[str, object, datetime | None]]] = []
            for field in comparable_date_fields:
                raw_value = " ".join((row.get(field) or "").strip().split())
                if not raw_value:
                    continue
                _reject_unsafe_unicode(raw_value, label="CSV date/time")
                parsed_aliases.append((field, _temporal_alias_value(raw_value)))
            if len(parsed_aliases) > 1:
                anchor_field, anchor_value = parsed_aliases[0]
                for other_field, other_value in parsed_aliases[1:]:
                    if not _temporal_aliases_compatible(anchor_value, other_value):
                        raise ValueError(
                            "CSV contains conflicting date/time metadata "
                            f"between {anchor_field!r} and {other_field!r}"
                        )

    # Multiple aliases are common in exported tables, but if two site/location
    # columns disagree on the same row then provenance is ambiguous. Reject rather
    # than silently privileging whichever alias has higher priority.
    if len(site_fields) > 1:
        for row in rows:
            row_sites = {
                _display_key(" ".join((row.get(field) or "").strip().split()))
                for field in site_fields
                if (row.get(field) or "").strip()
            }
            if len(row_sites) > 1:
                raise ValueError("CSV contains conflicting site/location metadata")

    def distinct_site_values(site_alias_fields: list[str], *, limit: int = 26) -> list[str]:
        values: list[str] = []
        seen: set[str] = set()
        for row in rows:
            chosen = ""
            for field in site_alias_fields:
                candidate = " ".join((row.get(field) or "").strip().split())
                if candidate:
                    chosen = candidate
                    break
            if not chosen:
                continue
            _reject_unsafe_unicode(chosen, label="CSV site")
            key = _display_key(chosen)
            if key in seen:
                continue
            seen.add(key)
            values.append(chosen)
            if len(values) >= limit:
                break
        return values

    site_probe = distinct_site_values(site_fields, limit=26)
    sites_complete = len(site_probe) < 26
    sites = site_probe[:25]
    site = sites[0] if sites_complete and len(sites) == 1 else None

    def distinct_date_values(date_alias_fields: list[str]) -> list[str]:
        values: list[str] = []
        seen: set[str] = set()
        for row in rows:
            chosen = ""
            # Alias priority is already encoded in date_alias_fields. Choose the
            # most precise/high-priority populated value *per row* so a sparse
            # timestamp column cannot hide dates present only in a fallback alias.
            for field in date_alias_fields:
                if _field_key(field) == "time":
                    continue
                candidate = " ".join((row.get(field) or "").strip().split())
                if candidate:
                    chosen = candidate
                    break
            # A standalone time-of-day column is useful provenance metadata but
            # cannot define a calendar date range by itself. Keep it out of the
            # range calculation rather than rejecting the entire context or
            # fabricating an arbitrary date.
            if not chosen:
                continue
            _reject_unsafe_unicode(chosen, label="CSV date/time")
            # Preserve original provenance text but deduplicate exact repeated
            # values; ordering is applied later using parsed UTC instants.
            if chosen in seen:
                continue
            seen.add(chosen)
            values.append(chosen)
        return values

    raw_dates = distinct_date_values(date_fields)
    dates = _sort_date_values(raw_dates) if raw_dates else []
    date_range = None
    if dates:
        date_range = dates[0] if len(dates) == 1 else f"{dates[0]} … {dates[-1]}"

    metadata_fields = set(site_fields) | set(date_fields)
    metadata_keys = {"latitude", "longitude", "lat", "lon", "id", "site id", "location id", "station id"}
    indicators = [
        f for f in fields
        if f not in metadata_fields and _field_key(f) not in metadata_keys
    ][:50]

    return AquaContext(
        source=AquaContextSource.RESILIENCE_COMPATIBLE_CSV,
        dataset_sha256=sha256_bytes(data),
        site=site,
        date_range=date_range,
        indicators=indicators,
        synthetic_demo=synthetic_demo,
        raw_summary={
            "rows": len(rows),
            "columns": fields[:80],
            "sites": sites,
            "sites_complete": sites_complete,
            "date_values_seen": len(dates),
            "site_field": site_field,
            "date_field": date_field,
        },
    )


_ALLOWED_FHIR_TYPES = {"Observation", "Location"}

# The prototype parses a narrow FHIR R4 environmental subset. Status is a
# recognized field, so accept only codes from the corresponding complete R5 code
# systems instead of silently treating arbitrary strings as provenance metadata.
# This is validation of a known FHIR field, not a claim of full FHIR conformance.
_OBSERVATION_STATUS_CODES = {
    "registered", "preliminary", "final", "amended", "corrected",
    "cancelled", "entered-in-error", "unknown",
}
_LOCATION_STATUS_CODES = {"active", "suspended", "inactive"}

# AquaSignal's FHIR adapter is intentionally environmental-only.  It is not a
# clinical ingestion surface, so patient/encounter/practitioner references are
# rejected anywhere in the supplied resource rather than merely ignored.
_CLINICAL_FHIR_TYPES = {
    "Patient", "Person", "RelatedPerson", "Encounter", "Practitioner",
    "PractitionerRole", "CareTeam", "Condition", "Procedure",
    "MedicationRequest", "MedicationStatement", "DiagnosticReport",
}
_FHIR_REFERENCE_TYPE = re.compile(r"(?:^|/)(?P<type>[A-Z][A-Za-z]+)/[^/?#]+(?:/|$|[?#])")


def _fhir_reference_type(reference: str) -> str | None:
    match = _FHIR_REFERENCE_TYPE.search(reference.strip())
    return match.group("type") if match else None


def _reject_clinical_fhir_content(resource: Any) -> None:
    stack: list[Any] = [resource]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            resource_type = value.get("resourceType")
            if isinstance(resource_type, str) and resource_type in _CLINICAL_FHIR_TYPES:
                raise ValueError(
                    f"Environmental FHIR context cannot contain clinical {resource_type} resources"
                )
            for key, child in value.items():
                if key == "reference" and isinstance(child, str):
                    target_type = _fhir_reference_type(child)
                    if target_type in _CLINICAL_FHIR_TYPES:
                        raise ValueError(
                            f"Environmental FHIR context cannot contain clinical {target_type} references"
                        )
                stack.append(child)
        elif isinstance(value, list):
            stack.extend(value)


def validate_fhir_structure(resource: Any, *, max_depth: int = 32, max_nodes: int = 20_000) -> None:
    """Bound JSON structural complexity before canonicalization or field parsing.

    FHIR permits extensions, so unknown fields remain allowed, but a provenance-only
    adapter should not accept arbitrarily deep/large object graphs that it never uses.
    The traversal is iterative to avoid recursion-limit failures on hostile nesting.
    """
    stack: list[tuple[Any, int]] = [(resource, 1)]
    seen = 0
    while stack:
        value, depth = stack.pop()
        seen += 1
        if seen > max_nodes:
            raise ValueError(f"FHIR JSON exceeds the {max_nodes:,}-node prototype limit")
        if depth > max_depth:
            raise ValueError(f"FHIR JSON exceeds the maximum nesting depth of {max_depth}")
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str):
                    raise ValueError("FHIR JSON object keys must be strings")
                stack.append((child, depth + 1))
        elif isinstance(value, list):
            for child in value:
                stack.append((child, depth + 1))
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError("FHIR JSON cannot contain NaN or Infinity")


def parse_oah_fhir_json(data: bytes, *, synthetic_demo: bool = False) -> AquaContext:
    """Parse a bounded environmental FHIR subset as provenance context.

    This parser intentionally does *not* claim OAH profile conformance. Exact OAH
    profile recognition, when configured, is handled at the API policy layer.
    """
    if len(data) > 1_000_000:
        raise ValueError("FHIR context exceeds the 1 MB prototype limit")
    def _pairs_no_duplicates(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f"FHIR JSON contains duplicate JSON object key: {key}")
            obj[key] = value
        return obj

    try:
        resource = json.loads(data, object_pairs_hook=_pairs_no_duplicates)
    except ValueError as exc:
        if "duplicate JSON object key" in str(exc):
            raise
        raise ValueError("Invalid or excessively nested JSON") from exc
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Invalid or excessively nested JSON") from exc
    if not isinstance(resource, dict):
        raise ValueError("FHIR resource must be a JSON object")
    validate_fhir_structure(resource)
    _reject_clinical_fhir_content(resource)
    resource_type = resource.get("resourceType")
    if resource_type not in _ALLOWED_FHIR_TYPES:
        raise ValueError("AquaSignal V1 accepts environmental Observation or Location resources only")

    meta_raw = resource.get("meta")
    meta = {} if meta_raw is None else meta_raw
    if not isinstance(meta, dict):
        raise ValueError("FHIR meta must be an object when present")
    profiles_raw = meta.get("profile")
    profiles = [] if profiles_raw is None else profiles_raw
    if not isinstance(profiles, list) or any(not isinstance(x, str) for x in profiles):
        raise ValueError("meta.profile must be a list of strings")
    profiles = [x.strip() for x in profiles if x.strip()]
    for profile_value in profiles:
        _reject_unsafe_unicode(profile_value, label="FHIR profile URI")
    if len(profiles) > 20:
        raise ValueError("FHIR meta.profile exceeds the 20-profile prototype limit")
    if any(len(x) > 500 for x in profiles):
        raise ValueError("FHIR profile URI must be at most 500 characters")
    profile = profiles[0] if profiles else None

    site = None
    subject_reference: str | None = None
    subject_display: str | None = None
    if resource_type == "Location":
        name = resource.get("name")
        resource_id = resource.get("id")
        if name is not None and not isinstance(name, str):
            raise ValueError("FHIR Location.name must be a string")
        if resource_id is not None and not isinstance(resource_id, str):
            raise ValueError("FHIR id must be a string")
        if name is not None:
            _reject_unsafe_unicode(name, label="FHIR Location.name")
        if resource_id is not None:
            _reject_unsafe_unicode(resource_id, label="FHIR id")
        if name is not None and len(name.strip()) > 200:
            raise ValueError("FHIR Location.name must be at most 200 characters")
        if resource_id is not None and len(resource_id.strip()) > 200:
            raise ValueError("FHIR id must be at most 200 characters")
        site = name or resource_id
    else:
        subject_raw = resource.get("subject")
        subject = {} if subject_raw is None else subject_raw
        if not isinstance(subject, dict):
            raise ValueError("FHIR Observation.subject must be an object when present")
        display = subject.get("display")
        reference = subject.get("reference")
        if display is not None and not isinstance(display, str):
            raise ValueError("FHIR Observation.subject.display must be a string")
        if reference is not None and not isinstance(reference, str):
            raise ValueError("FHIR Observation.subject.reference must be a string")
        if display is not None:
            _reject_unsafe_unicode(display, label="FHIR Observation.subject.display")
        if reference is not None:
            _reject_unsafe_unicode(reference, label="FHIR Observation.subject.reference")
        if display is not None and len(display.strip()) > 200:
            raise ValueError("FHIR Observation.subject.display must be at most 200 characters")
        if reference is not None and len(reference.strip()) > 200:
            raise ValueError("FHIR Observation.subject.reference must be at most 200 characters")
        if reference is not None and _fhir_reference_type(reference) != "Location":
            raise ValueError("FHIR Observation.subject.reference must target an environmental Location")
        subject_reference = reference.strip() if isinstance(reference, str) and reference.strip() else None
        subject_display = display.strip() if isinstance(display, str) and display.strip() else None
        site = subject_display or subject_reference

    indicators: list[str] = []
    code_raw = resource.get("code")
    code = {} if code_raw is None else code_raw
    if not isinstance(code, dict):
        raise ValueError("FHIR code must be an object when present")
    text_value = code.get("text")
    if text_value is not None:
        if not isinstance(text_value, str):
            raise ValueError("FHIR code.text must be a string")
        _reject_unsafe_unicode(text_value, label="FHIR code.text")
        if len(text_value.strip()) > 200:
            raise ValueError("FHIR code.text must be at most 200 characters")
        if text_value.strip():
            indicators.append(text_value.strip())
    coding_raw = code.get("coding")
    coding = [] if coding_raw is None else coding_raw
    if not isinstance(coding, list):
        raise ValueError("FHIR code.coding must be a list")
    if len(coding) > 200:
        raise ValueError("FHIR code.coding exceeds the 200-entry prototype limit")
    for item in coding:
        if not isinstance(item, dict):
            raise ValueError("FHIR code.coding entries must be objects")
        display = item.get("display") or item.get("code")
        if display is not None and not isinstance(display, str):
            raise ValueError("FHIR coding display/code must be a string")
        if isinstance(display, str):
            _reject_unsafe_unicode(display, label="FHIR coding display/code")
        if isinstance(display, str) and len(display.strip()) > 200:
            raise ValueError("FHIR coding display/code must be at most 200 characters")
        if display:
            indicators.append(display)

    resource_id = resource.get("id")
    if resource_id is not None and not isinstance(resource_id, str):
        raise ValueError("FHIR id must be a string")
    if resource_id is not None:
        _reject_unsafe_unicode(resource_id, label="FHIR id")
    if resource_id is not None and len(resource_id.strip()) > 200:
        raise ValueError("FHIR id must be at most 200 characters")

    status = resource.get("status")
    if status is not None and not isinstance(status, str):
        raise ValueError("FHIR status must be a string when present")
    if isinstance(status, str):
        _reject_unsafe_unicode(status, label="FHIR status")
        if len(status) > 80:
            raise ValueError("FHIR status must be at most 80 characters")
        allowed_statuses = (
            _OBSERVATION_STATUS_CODES if resource_type == "Observation" else _LOCATION_STATUS_CODES
        )
        if status not in allowed_statuses:
            raise ValueError(
                f"FHIR {resource_type}.status is not a recognized FHIR R4 status code: {status!r}"
            )

    return AquaContext(
        source=AquaContextSource.ENVIRONMENTAL_FHIR_JSON,
        dataset_sha256=sha256_bytes(data),
        site=site,
        indicators=list(dict.fromkeys(indicators))[:50],
        resource_type=resource_type,
        profile=profile,
        resource_id=resource_id,
        synthetic_demo=synthetic_demo,
        raw_summary={
            "profiles": profiles,
            "profile_count": len(profiles),
            "status": status,
            "subject_reference": subject_reference,
            "subject_display": subject_display,
        },
    )


def assess_context_alignment(context: AquaContext, contract) -> tuple[str, str]:
    """Return MATCH/UNKNOWN/MISMATCH without inferring environmental risk.

    Single-site contexts compare directly. Resilience-compatible multi-site CSV
    contexts use the server-derived site inventory: a known member can MATCH, a
    known non-member can MISMATCH only when that inventory is complete, and partial
    inventories fail closed to UNKNOWN.
    """
    from aquasignal.domain.freshwater import aqua_canonical_place

    named: list[str] = []
    for area in contract.affected_areas:
        low = area.casefold()
        if low.startswith(("stream ", "river ", "creek ", "site ", "zone ")):
            named.append(aqua_canonical_place(area))
    if not named:
        return "UNKNOWN", "Advisory has no comparable named site scope; context remains provenance only."

    # For an Observation, subject.display is only a human-readable representation of
    # a Location reference. AquaSignal deliberately does not dereference FHIR
    # references, so treating that display as verified identity could produce a false
    # MATCH when reference and display disagree. Keep it as provenance and report
    # alignment UNKNOWN. A direct Location resource may still establish its own name.
    if (
        context.source == AquaContextSource.ENVIRONMENTAL_FHIR_JSON
        and context.resource_type == "Observation"
    ):
        return (
            "UNKNOWN",
            "FHIR Observation subject display/reference is provenance-only; AquaSignal does not dereference the Location to verify site identity.",
        )

    def _base_waterbody(area: str) -> str:
        for marker in (" upstream of ", " downstream of "):
            if marker in area:
                return area.split(marker, 1)[0].strip()
        return area

    advisory_bases = list(dict.fromkeys(_base_waterbody(area) for area in named))

    context_sites: list[str] = []
    complete = True
    if context.site:
        context_sites = [aqua_canonical_place(context.site)]
    elif context.source == AquaContextSource.RESILIENCE_COMPATIBLE_CSV:
        raw_sites = context.raw_summary.get("sites") or []
        if isinstance(raw_sites, list):
            context_sites = [
                aqua_canonical_place(value)
                for value in raw_sites
                if isinstance(value, str) and value.strip()
            ]
        complete = bool(context.raw_summary.get("sites_complete", False))

    comparable_sites = [
        site
        for site in context_sites
        if site.startswith(("stream ", "river ", "creek ", "site ", "zone "))
    ]
    if not comparable_sites:
        return "UNKNOWN", "Environmental context does not expose a comparable site name."

    def _scope_parts(area: str) -> tuple[str, str | None, str | None]:
        for marker in (" upstream of ", " downstream of "):
            if marker in area:
                base, landmark = area.split(marker, 1)
                return base.strip(), marker.strip(), landmark.strip()
        return area, None, None

    def _context_covers(advisory_area: str, context_site: str) -> bool:
        advisory_base, advisory_relation, advisory_landmark = _scope_parts(advisory_area)
        context_base, context_relation, context_landmark = _scope_parts(context_site)
        if advisory_base != context_base:
            return False
        # A base-waterbody context may safely bind an advisory that adds a supported
        # upstream/downstream qualifier.  The reverse is not true: a context already
        # narrowed to a relational segment must not silently authorize an advisory
        # broadened to the whole waterbody or moved to a different relation/landmark.
        if context_relation is None:
            return True
        return (
            advisory_relation == context_relation
            and advisory_landmark == context_landmark
        )

    matched = [area for area in named if any(_context_covers(area, site) for site in comparable_sites)]
    missing = [area for area in named if not any(_context_covers(area, site) for site in comparable_sites)]

    if matched and not missing:
        detail = "All named advisory waterbody scopes are covered by the bound environmental context."
        if any(_base_waterbody(area) != area for area in named) and all(
            _base_waterbody(site) == site for site in comparable_sites
        ):
            detail += " The advisory adds a supported upstream/downstream relational scope within the bound base waterbody."
        return "MATCH", detail
    if matched and missing:
        return "UNKNOWN", "Advisory names multiple freshwater scopes and only some are covered by the bound context."
    if complete:
        return "MISMATCH", f"Advisory site scope {named!r} is not covered by bound context sites {sorted(comparable_sites)!r}."
    return "UNKNOWN", "Advisory site scope is not present in the bounded context-site sample, but the multi-site inventory was truncated."

