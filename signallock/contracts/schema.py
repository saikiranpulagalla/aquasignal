from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)


class ActionType(StrEnum):
    SHELTER = "SHELTER"
    EVACUATE = "EVACUATE"
    PREPARE = "PREPARE"
    EXECUTE = "EXECUTE"
    AVOID = "AVOID"
    MONITOR = "MONITOR"
    ALL_CLEAR = "ALL_CLEAR"
    OTHER = "OTHER"


class Decision(StrEnum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class Severity(StrEnum):
    EXTREME = "Extreme"
    SEVERE = "Severe"
    MODERATE = "Moderate"
    MINOR = "Minor"
    UNKNOWN = "Unknown"


class Urgency(StrEnum):
    IMMEDIATE = "Immediate"
    EXPECTED = "Expected"
    FUTURE = "Future"
    PAST = "Past"
    UNKNOWN = "Unknown"


class Certainty(StrEnum):
    OBSERVED = "Observed"
    LIKELY = "Likely"
    POSSIBLE = "Possible"
    UNLIKELY = "Unlikely"
    UNKNOWN = "Unknown"


class QuantityRelation(StrEnum):
    GREATER_THAN = "GreaterThan"
    GREATER_OR_EQUAL = "GreaterOrEqual"
    LESS_THAN = "LessThan"
    LESS_OR_EQUAL = "LessOrEqual"
    EQUAL = "Equal"
    UNKNOWN = "Unknown"


class Modality(StrEnum):
    MUST = "MUST"
    SHOULD = "SHOULD"
    MAY = "MAY"
    PROHIBITED = "PROHIBITED"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNKNOWN = "UNKNOWN"


class TemporalOperator(StrEnum):
    UNTIL = "UNTIL"
    BY = "BY"
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    AT = "AT"
    STARTING = "STARTING"
    ON = "ON"
    UNKNOWN = "UNKNOWN"


class LogicOperator(StrEnum):
    SINGLE = "SINGLE"
    AND = "AND"
    OR = "OR"


class TemporalConstraint(StrictModel):
    operator: TemporalOperator
    time: str = Field(min_length=1, max_length=80)


class EvidenceSpan(StrictModel):
    quote: str = Field(min_length=1, max_length=1000)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> "EvidenceSpan":
        if self.end_char <= self.start_char:
            raise ValueError("end_char must be greater than start_char")
        return self


class Hazard(StrictModel):
    type: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    evidence: EvidenceSpan | None = None


class Quantity(StrictModel):
    value: float
    unit: str = Field(min_length=1, max_length=40)
    relation: QuantityRelation = QuantityRelation.UNKNOWN
    meaning: str | None = Field(default=None, max_length=250)
    evidence: EvidenceSpan | None = None


class ExceptionRule(StrictModel):
    text: str = Field(min_length=1, max_length=600)
    evidence: EvidenceSpan | None = None


class Action(StrictModel):
    """One scoped operational directive.

    Legacy v0.2 fields remain intact.  The added fields bind the predicate to the
    audience/area/quantity/exception/time/logic that modify *this* directive, so
    verification no longer compares independent bags of facts.
    """

    type: ActionType
    verb: str = Field(min_length=1, max_length=80)
    object: str | None = Field(default=None, max_length=250)
    destination: str | None = Field(default=None, max_length=250)
    condition: str | None = Field(default=None, max_length=500)
    deadline: str | None = Field(default=None, max_length=80)
    negated: bool = False
    evidence: EvidenceSpan | None = None

    modality: Modality = Modality.UNKNOWN
    scoped_audience: list[str] = Field(default_factory=list)
    scoped_areas: list[str] = Field(default_factory=list)
    temporal_operator: TemporalOperator | None = None
    temporal_constraints: list[TemporalConstraint] = Field(default_factory=list)
    bound_quantities: list[Quantity] = Field(default_factory=list)
    bound_exceptions: list[str] = Field(default_factory=list)
    sequence_group: str | None = Field(default=None, max_length=80)
    sequence_index: int | None = Field(default=None, ge=0)
    logic_group: str | None = Field(default=None, max_length=80)
    logic_operator: LogicOperator = LogicOperator.SINGLE

    @field_validator("scoped_audience", "scoped_areas", "bound_exceptions")
    @classmethod
    def no_blank_scope_items(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("blank scoped directive item is not allowed")
        return value

    @model_validator(mode="after")
    def normalize_temporal_fields(self) -> "Action":
        # v0.5 supports multiple simultaneous constraints while preserving legacy
        # deadline/temporal_operator for old payloads and clients.
        if self.temporal_constraints:
            first = self.temporal_constraints[0]
            if self.deadline is None:
                self.deadline = first.time
            if self.temporal_operator is None:
                self.temporal_operator = first.operator
        elif self.deadline and self.temporal_operator:
            self.temporal_constraints = [TemporalConstraint(operator=self.temporal_operator, time=self.deadline)]
        return self




def _contract_key(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())



def _scope_key(values: list[str]) -> tuple[str, ...]:
    return tuple(sorted(_contract_key(v) for v in values if _contract_key(v)))



def _action_contradiction_key(action: Action) -> tuple:
    return (
        action.type.value,
        _contract_key(action.verb),
        _contract_key(action.object),
        _contract_key(action.destination),
        _scope_key(action.scoped_audience),
        _scope_key(action.scoped_areas),
        _contract_key(action.condition),
        tuple((x.operator.value, _contract_key(x.time)) for x in action.temporal_constraints),
        action.temporal_operator.value if action.temporal_operator else "",
        _contract_key(action.deadline),
    )


class SafetyContract(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    language: str = Field(default="en", min_length=2, max_length=20)
    hazard: Hazard | None = None
    audience: list[str] = Field(default_factory=list)
    affected_areas: list[str] = Field(default_factory=list)
    required_actions: list[Action] = Field(default_factory=list)
    prohibited_actions: list[Action] = Field(default_factory=list)
    urgency: Urgency = Urgency.UNKNOWN
    severity: Severity = Severity.UNKNOWN
    certainty: Certainty = Certainty.UNKNOWN
    effective_at: datetime | None = None
    expires_at: datetime | None = None
    quantities: list[Quantity] = Field(default_factory=list)
    exceptions: list[ExceptionRule] = Field(default_factory=list)
    unresolved_operational_text: list[str] = Field(default_factory=list)
    source_id: str | None = Field(default=None, max_length=200)

    @field_validator("audience", "affected_areas", "unresolved_operational_text")
    @classmethod
    def no_blank_items(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("blank list item is not allowed")
        return value

    @model_validator(mode="after")
    def semantic_consistency(self) -> "SafetyContract":
        if self.effective_at and self.expires_at and self.expires_at < self.effective_at:
            raise ValueError("expires_at cannot precede effective_at")

        # Backward compatibility: v0.2 payloads did not carry modality.  Infer it
        # from list membership, then keep it immutable as an explicit semantic slot.
        for action in self.required_actions:
            if action.negated:
                raise ValueError("required_actions cannot contain negated actions")
            if action.modality == Modality.UNKNOWN and "modality" not in action.model_fields_set:
                action.modality = Modality.MUST
            if action.modality == Modality.PROHIBITED:
                raise ValueError("required_actions cannot use PROHIBITED modality")
        for action in self.prohibited_actions:
            if not action.negated:
                raise ValueError("prohibited_actions must use negated=true")
            if action.modality == Modality.UNKNOWN and "modality" not in action.model_fields_set:
                action.modality = Modality.PROHIBITED
            if action.modality != Modality.PROHIBITED:
                raise ValueError("prohibited_actions must use PROHIBITED modality")

        required = {_action_contradiction_key(a) for a in self.required_actions}
        prohibited = {_action_contradiction_key(a) for a in self.prohibited_actions}
        if required & prohibited:
            raise ValueError("contract contains a directly contradictory required/prohibited action")
        return self


class VerificationSignal(StrictModel):
    field: str
    status: Literal["PASS", "WARN", "FAIL", "UNKNOWN"]
    criticality: Literal["P0", "P1", "P2"]
    expected: str | None = None
    observed: str | None = None
    reason: str
    detector: str


class VerificationResult(StrictModel):
    decision: Decision
    signals: list[VerificationSignal]
    critical_failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: str
    source_contract: SafetyContract
    candidate_contract: SafetyContract
