# backend/app/models/candidate.py

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class CandidateStatus(str, Enum):
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW = "interview"
    OFFER = "offer"
    HIRED = "hired"
    REJECTED = "rejected"


ALLOWED_TRANSITIONS: dict[CandidateStatus, list[CandidateStatus]] = {
    CandidateStatus.APPLIED: [
        CandidateStatus.SCREENING,
        CandidateStatus.REJECTED,
    ],
    CandidateStatus.SCREENING: [
        CandidateStatus.INTERVIEW,
        CandidateStatus.REJECTED,
    ],
    CandidateStatus.INTERVIEW: [
        CandidateStatus.OFFER,
        CandidateStatus.REJECTED,
    ],
    CandidateStatus.OFFER: [
        CandidateStatus.HIRED,
        CandidateStatus.REJECTED,
    ],
    CandidateStatus.HIRED: [],
    CandidateStatus.REJECTED: [],
}


class CandidateBase(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None

    current_position: str | None = None
    domain: str | None = None

    job_id: UUID | None = None

    skills: list[str] = Field(default_factory=list)
    extracted_skills: list[str] = Field(default_factory=list)

    experience_years: int | None = 0
    years_experience: int | None = 0

    highest_degree: str | None = None

    certifications: list[str] = Field(default_factory=list)

    ai_extracted_data: dict[str, Any] | None = None

    @field_validator("email", mode="before")
    @classmethod
    def clean_email(cls, v):
        if not v:
            return None

        if isinstance(v, str):
            v = v.strip().replace(" ", "")

        return v

    class Config:
        from_attributes = True


class CandidateCreate(CandidateBase):
    cv_file_url: str | None = None
    drive_file_id: str | None = None


class CandidateUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None

    current_position: str | None = None
    domain: str | None = None

    skills: list[str] | None = None
    extracted_skills: list[str] | None = None

    experience_years: int | None = None
    years_experience: int | None = None

    highest_degree: str | None = None

    certifications: list[str] | None = None

    ai_extracted_data: dict[str, Any] | None = None

    job_id: UUID | None = None


class CandidateStatusTransition(BaseModel):
    new_status: CandidateStatus
    note: str | None = None


class CandidateResponse(CandidateBase):
    id: UUID

    status: CandidateStatus

    score: float | None = None

    cv_file_url: str | None = None
    drive_file_id: str | None = None
    processing_status: str | None = None

    created_at: datetime
    updated_at: datetime
    
    certifications: list[str] = Field(default_factory=list)
    education: list = Field(default_factory=list)
    projects: list = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    work_history: list = Field(default_factory=list)
    dimension_scores: dict = Field(default_factory=dict)

    class Config:
        from_attributes = True