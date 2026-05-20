import pytest
from fastapi import HTTPException
from app.core.state_machine import validate_transition


def test_valid_applied_to_screening():
    validate_transition("applied", "screening")


def test_valid_screening_to_rejected():
    validate_transition("screening", "rejected")


def test_invalid_applied_to_offer():
    with pytest.raises(HTTPException) as exc:
        validate_transition("applied", "offer")
    assert exc.value.status_code == 422


def test_terminal_hired():
    with pytest.raises(HTTPException) as exc:
        validate_transition("hired", "screening")
    assert "terminal state" in exc.value.detail.lower()


def test_terminal_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_transition("rejected", "interview")
    assert exc.value.status_code == 422


def test_invalid_status_value():
    with pytest.raises(HTTPException) as exc:
        validate_transition("applied", "ghost")
    assert exc.value.status_code == 422