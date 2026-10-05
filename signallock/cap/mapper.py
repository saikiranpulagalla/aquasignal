from __future__ import annotations

from signallock.cap.parser import CAPAlert, CAPInfo
from signallock.contracts.extractor import HeuristicExtractor
from signallock.contracts.schema import (
    Action,
    ActionType,
    Certainty,
    Hazard,
    SafetyContract,
    Severity,
    Urgency,
)


_RESPONSE_TYPE_MAP = {
    "shelter": ActionType.SHELTER,
    "evacuate": ActionType.EVACUATE,
    "prepare": ActionType.PREPARE,
    "execute": ActionType.EXECUTE,
    "avoid": ActionType.AVOID,
    "monitor": ActionType.MONITOR,
    "allclear": ActionType.ALL_CLEAR,
    "none": ActionType.OTHER,
}


def _enum_or_unknown(enum_cls, value: str | None):
    if not value:
        return enum_cls.UNKNOWN
    for member in enum_cls:
        if member.value.casefold() == value.casefold():
            return member
    return enum_cls.UNKNOWN


def _unique_text(*groups: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            key = value.casefold().strip()
            if key and key not in seen:
                seen.add(key)
                out.append(value.strip())
    return out


def cap_info_seed_contract(alert: CAPAlert, info: CAPInfo) -> SafetyContract:
    """Build an authoritative contract from CAP structure plus instruction semantics.

    Structured CAP metadata wins for hazard/timing/audience/areas. The instruction is
    additionally parsed for concrete protective/prohibited actions, quantities and exceptions.
    """
    extracted = SafetyContract(language=info.language, source_id=alert.identifier)
    if info.instruction:
        if info.language.split("-")[0].casefold() == "en":
            extracted = HeuristicExtractor().extract(info.instruction, language="en", source_id=alert.identifier)
        else:
            # Offline CAP verification has no multilingual semantic extractor. Never let
            # structured metadata make an unchecked non-English instruction look safe.
            extracted = SafetyContract(
                language=info.language,
                source_id=alert.identifier,
                unresolved_operational_text=[info.instruction],
            )

    actions = list(extracted.required_actions)
    present_types = {a.type for a in actions}
    prohibited_types = {a.type for a in extracted.prohibited_actions}
    for response in info.response_types:
        action_type = _RESPONSE_TYPE_MAP.get(response.replace(" ", "").casefold(), ActionType.OTHER)
        # Instruction-level semantics are more specific. Avoid duplicating a high-level response type.
        if action_type in present_types:
            continue
        if action_type == ActionType.AVOID and (ActionType.AVOID in prohibited_types or extracted.prohibited_actions):
            continue
        actions.append(Action(type=action_type, verb=response, object=None))
        present_types.add(action_type)

    structured_audience = [x.strip() for x in (info.audience or "").split(",") if x.strip()]
    final_audience = _unique_text(structured_audience, extracted.audience)
    final_areas = _unique_text(info.areas, extracted.affected_areas)
    # CAP info-level area semantics apply to every protective directive in that info
    # block. Bind them explicitly so a transformed instruction cannot swap actions
    # between areas while preserving the same global sets.
    for action in actions + list(extracted.prohibited_actions):
        if not action.scoped_areas and final_areas:
            action.scoped_areas = list(final_areas)
        if not action.scoped_audience and len(final_audience) == 1:
            action.scoped_audience = list(final_audience)
    return SafetyContract(
        language=info.language,
        source_id=alert.identifier,
        hazard=Hazard(type=info.event or "unknown", description=info.headline or info.description) if info.event else extracted.hazard,
        audience=final_audience,
        affected_areas=final_areas,
        required_actions=actions,
        prohibited_actions=extracted.prohibited_actions,
        urgency=_enum_or_unknown(Urgency, info.urgency),
        severity=_enum_or_unknown(Severity, info.severity),
        certainty=_enum_or_unknown(Certainty, info.certainty),
        effective_at=info.effective,
        expires_at=info.expires,
        quantities=extracted.quantities,
        exceptions=extracted.exceptions,
        unresolved_operational_text=extracted.unresolved_operational_text,
    )
