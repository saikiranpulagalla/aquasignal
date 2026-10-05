from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from defusedxml.ElementTree import fromstring


MAX_CAP_BYTES = 1_000_000
CAP12_NS = "urn:oasis:names:tc:emergency:cap:1.2"
_VALID_STATUS = {"Actual", "Exercise", "System", "Test", "Draft"}
_VALID_MSG_TYPE = {"Alert", "Update", "Cancel", "Ack", "Error"}
_VALID_SCOPE = {"Public", "Restricted", "Private"}
_VALID_URGENCY = {"Immediate", "Expected", "Future", "Past", "Unknown"}
_VALID_SEVERITY = {"Extreme", "Severe", "Moderate", "Minor", "Unknown"}
_VALID_CERTAINTY = {"Observed", "Likely", "Possible", "Unlikely", "Unknown"}
_VALID_RESPONSE = {"Shelter", "Evacuate", "Prepare", "Execute", "Avoid", "Monitor", "AllClear", "None"}


@dataclass(slots=True)
class CAPInfo:
    language: str = "en"
    category: list[str] = field(default_factory=list)
    event: str | None = None
    response_types: list[str] = field(default_factory=list)
    urgency: str | None = None
    severity: str | None = None
    certainty: str | None = None
    onset: datetime | None = None
    effective: datetime | None = None
    expires: datetime | None = None
    audience: str | None = None
    headline: str | None = None
    description: str | None = None
    instruction: str | None = None
    areas: list[str] = field(default_factory=list)
    polygons: list[str] = field(default_factory=list)
    circles: list[str] = field(default_factory=list)
    geocodes: list[tuple[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class CAPAlert:
    identifier: str
    sender: str
    sent: datetime
    status: str
    msg_type: str
    scope: str
    infos: list[CAPInfo]
    references: str | None = None
    restriction: str | None = None
    addresses: list[str] = field(default_factory=list)
    namespace: str | None = None


def _namespace(tag: str) -> str | None:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(parent, name: str) -> Iterable:
    for child in list(parent):
        if _local(child.tag) == name:
            yield child


def _first_text(parent, name: str) -> str | None:
    for child in _children(parent, name):
        if child.text is not None:
            text = child.text.strip()
            return text or None
    return None


def _all_text(parent, name: str) -> list[str]:
    values: list[str] = []
    for child in _children(parent, name):
        if child.text:
            text = child.text.strip()
            if text:
                values.append(text)
    return values


def _parse_dt(value: str | None, *, field_name: str, required: bool = False, profile_strict: bool = False) -> datetime | None:
    if not value:
        if required:
            raise ValueError(f"CAP {field_name} is required")
        return None
    if profile_strict:
        # CAP 1.2 profile used here requires an explicit numeric UTC offset.  Do not
        # silently reinterpret a local time or alphabetic Z in the safety boundary.
        if value.endswith("Z") or not re.search(r"[+-]\d{2}:\d{2}$", value):
            raise ValueError(f"CAP {field_name} must include an explicit numeric timezone offset")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid CAP {field_name} datetime: {value}") from exc
    if profile_strict and parsed.tzinfo is None:
        raise ValueError(f"CAP {field_name} must be timezone-aware")
    return parsed


def _required(root, name: str) -> str:
    value = _first_text(root, name)
    if not value:
        raise ValueError(f"CAP {name} is required")
    return value


def _validate_enum(name: str, value: str | None, allowed: set[str], *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"CAP {name} is required")
        return None
    if value not in allowed:
        raise ValueError(f"Invalid CAP {name}: {value}")
    return value


def parse_cap_xml(xml: str | bytes, *, profile_strict: bool = False) -> CAPAlert:
    raw = xml.encode("utf-8") if isinstance(xml, str) else xml
    if len(raw) > MAX_CAP_BYTES:
        raise ValueError(f"CAP payload exceeds {MAX_CAP_BYTES} bytes")
    try:
        root = fromstring(raw)
    except Exception as exc:
        raise ValueError("Invalid or unsafe CAP XML") from exc
    if _local(root.tag) != "alert":
        raise ValueError("Root element must be CAP alert")

    namespace = _namespace(root.tag)
    if profile_strict and namespace != CAP12_NS:
        raise ValueError(f"CAP 1.2 namespace is required: {CAP12_NS}")

    identifier = _required(root, "identifier")
    sender = _required(root, "sender")
    sent = _parse_dt(_required(root, "sent"), field_name="sent", required=True, profile_strict=profile_strict)
    assert sent is not None
    status = _validate_enum("status", _required(root, "status"), _VALID_STATUS, required=True)
    msg_type = _validate_enum("msgType", _required(root, "msgType"), _VALID_MSG_TYPE, required=True)
    scope = _validate_enum("scope", _required(root, "scope"), _VALID_SCOPE, required=True)
    assert status and msg_type and scope

    references = _first_text(root, "references")
    restriction = _first_text(root, "restriction")
    addresses = _all_text(root, "addresses")
    if profile_strict:
        if scope == "Restricted" and not restriction:
            raise ValueError("CAP Restricted scope requires restriction")
        if scope == "Private" and not addresses:
            raise ValueError("CAP Private scope requires addresses")
        if msg_type in {"Update", "Cancel"} and not references:
            raise ValueError(f"CAP {msg_type} message requires references")

    if profile_strict:
        for name in ("identifier", "sender", "sent", "status", "msgType", "scope", "references", "restriction"):
            if len(list(_children(root, name))) > 1:
                raise ValueError(f"CAP alert/{name} must not be duplicated in strict profile")

    infos: list[CAPInfo] = []
    for info_el in _children(root, "info"):
        categories = _all_text(info_el, "category")
        if not categories:
            raise ValueError("CAP info/category is required")
        event = _first_text(info_el, "event")
        if not event:
            raise ValueError("CAP info/event is required")

        areas: list[str] = []
        polygons: list[str] = []
        circles: list[str] = []
        geocodes: list[tuple[str, str]] = []
        for area_el in _children(info_el, "area"):
            desc = _first_text(area_el, "areaDesc")
            if not desc:
                raise ValueError("CAP area/areaDesc is required")
            if desc not in areas:
                areas.append(desc)
            polygons.extend(_all_text(area_el, "polygon"))
            circles.extend(_all_text(area_el, "circle"))
            for geocode_el in _children(area_el, "geocode"):
                name = _first_text(geocode_el, "valueName")
                value = _first_text(geocode_el, "value")
                if profile_strict and (not name or not value):
                    raise ValueError("CAP geocode requires valueName and value")
                if name and value:
                    geocodes.append((name, value))

        if profile_strict:
            for name in ("language", "event", "urgency", "severity", "certainty", "onset", "effective", "expires", "audience", "headline", "description", "instruction"):
                if len(list(_children(info_el, name))) > 1:
                    raise ValueError(f"CAP info/{name} must not be duplicated in strict profile")

        response_types = _all_text(info_el, "responseType")
        for response in response_types:
            _validate_enum("responseType", response, _VALID_RESPONSE)

        urgency = _validate_enum("urgency", _first_text(info_el, "urgency"), _VALID_URGENCY, required=True)
        severity = _validate_enum("severity", _first_text(info_el, "severity"), _VALID_SEVERITY, required=True)
        certainty = _validate_enum("certainty", _first_text(info_el, "certainty"), _VALID_CERTAINTY, required=True)
        infos.append(CAPInfo(
            language=_first_text(info_el, "language") or "en",
            category=categories,
            event=event,
            response_types=response_types,
            urgency=urgency,
            severity=severity,
            certainty=certainty,
            onset=_parse_dt(_first_text(info_el, "onset"), field_name="onset", profile_strict=profile_strict),
            effective=_parse_dt(_first_text(info_el, "effective"), field_name="effective", profile_strict=profile_strict),
            expires=_parse_dt(_first_text(info_el, "expires"), field_name="expires", profile_strict=profile_strict),
            audience=_first_text(info_el, "audience"),
            headline=_first_text(info_el, "headline"),
            description=_first_text(info_el, "description"),
            instruction=_first_text(info_el, "instruction"),
            areas=areas,
            polygons=polygons,
            circles=circles,
            geocodes=geocodes,
        ))

    return CAPAlert(
        identifier=identifier,
        sender=sender,
        sent=sent,
        status=status,
        msg_type=msg_type,
        scope=scope,
        infos=infos,
        references=references,
        restriction=restriction,
        addresses=addresses,
        namespace=namespace,
    )
