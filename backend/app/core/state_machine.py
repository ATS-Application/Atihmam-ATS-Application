# backend/app/core/state_machine.py
from fastapi import HTTPException, status
from app.models.candidate import CandidateStatus, ALLOWED_TRANSITIONS


def validate_transition(current: str, target: str) -> None:
    try:
        current_enum = CandidateStatus(current)
        target_enum = CandidateStatus(target)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status value: '{current}' or '{target}'",
        )

    allowed = ALLOWED_TRANSITIONS.get(current_enum, [])

    if target_enum not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Transition '{current}' → '{target}' is not allowed. "
                f"Allowed: {[s.value for s in allowed] or 'none (terminal state)'}"
            ),
        )