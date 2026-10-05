import pytest
from pydantic import ValidationError

from signallock.contracts.schema import Action, ActionType, SafetyContract


def test_required_action_cannot_be_negated():
    with pytest.raises(ValidationError):
        SafetyContract(required_actions=[Action(type=ActionType.SHELTER, verb="shelter", negated=True)])


def test_prohibited_action_must_be_negated():
    with pytest.raises(ValidationError):
        SafetyContract(prohibited_actions=[Action(type=ActionType.AVOID, verb="enter", object="tunnel", negated=False)])


def test_direct_contradiction_rejected():
    with pytest.raises(ValidationError):
        SafetyContract(
            required_actions=[Action(type=ActionType.SHELTER, verb="shelter", destination="indoors")],
            prohibited_actions=[Action(type=ActionType.SHELTER, verb="shelter", destination="indoors", negated=True)],
        )
