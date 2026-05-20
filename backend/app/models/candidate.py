# app/models/candidate.py

from pydantic import BaseModel, EmailStr, Field
from typing import Any
from uuid import UUID
from datetime import datetime
from enum import Enum


class CandidateStatus(str, Enum):
    APPLIED    = "applied"
    SCREENING  = "screening"
    INTERVIEW  = "interview"
    OFFER      = "offer"
    HIRED      = "hired"
    REJECTED   = "rejected"


ALLOWED_TRANSITIONS: dict[CandidateStatus, list[CandidateStatus]] = {
    CandidateStatus.APPLIED:   [CandidateStatus.SCREENING, CandidateStatus.REJECTED],
    CandidateStatus.SCREENING: [CandidateStatus.INTERVIEW, CandidateStatus.REJECTED],
    CandidateStatus.INTERVIEW: [CandidateStatus.OFFER,     CandidateStatus.REJECTED],
    CandidateStatus.OFFER:     [CandidateStatus.HIRED,     CandidateStatus.REJECTED],
    CandidateStatus.HIRED:     [],
    CandidateStatus.REJECTED:  [],
}


class CandidateBase(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    current_position: str | None = None
    skills: list[str] | None = Field(default_factory=list)
    experience_years: int | None = None
    job_id: UUID | None = None


class CandidateCreate(CandidateBase):
    cv_file_url: str | None = None
    drive_file_id: str | None = None


class CandidateUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    current_position: str | None = None
    skills: list[str] | None = None
    experience_years: int | None = None
    job_id: UUID | None = None


class CandidateStatusTransition(BaseModel):
    new_status: CandidateStatus
    note: str | None = None


class CandidateResponse(CandidateBase):
    id: UUID
    status: CandidateStatus
    score: float | None = None
    cv_file_url: str | None = None
    ai_extracted_data: dict[str, Any] | None = None
    drive_file_id: str | None = None
    created_at: datetime
    updated_at: datetime