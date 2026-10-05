from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from signallock.contracts.schema import Action, ActionType, EvidenceSpan, SafetyContract


def test_contract_round_trip():
    contract = SafetyContract(
        language="en",
        required_actions=[Action(type=ActionType.SHELTER, verb="shelter", destination="indoors")],
    )
    assert SafetyContract.model_validate_json(contract.model_dump_json()) == contract


def test_invalid_action_enum_rejected():
    with pytest.raises(ValidationError):
        Action(type="RUN_AWAY", verb="run")


def test_invalid_evidence_range_rejected():
    with pytest.raises(ValidationError):
        EvidenceSpan(quote="x", start_char=5, end_char=5)


def test_expiry_before_effective_rejected():
    with pytest.raises(ValidationError):
        SafetyContract(
            effective_at=datetime(2026, 9, 10, 12, tzinfo=timezone.utc),
            expires_at=datetime(2026, 9, 10, 11, tzinfo=timezone.utc),
        )


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        SafetyContract(language="en", invented=True)
