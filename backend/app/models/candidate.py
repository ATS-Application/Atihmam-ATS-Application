# backend/app/models/candidate.py

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Union
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
    s: [t for t in CandidateStatus if t != s]
    for s in CandidateStatus
}


class LanguageEntry(BaseModel):
    """Représente une langue, sous forme dict ou str dans la DB."""
    language: str = ""
    level: str | None = None

    @classmethod
    def from_any(cls, v: Any) -> str:
        """Convertit dict ou str en chaîne lisible."""
        if isinstance(v, dict):
            lang  = v.get("language") or v.get("name") or ""
            level = v.get("level") or ""
            return f"{lang} ({level})" if lang and level else lang
        return str(v) if v else ""


# Type souple : une langue peut être une str ou un dict
LanguageItem = Union[str, dict]


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
            
            if "@" in v:
                local, _, domain = v.partition("@")
                domain = domain.replace(",", ".")
                v = f"{local}@{domain}"

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
    locked_at: datetime | None = None

    created_at: datetime
    updated_at: datetime
    
    certifications: list[str] = Field(default_factory=list)
    education: list = Field(default_factory=list)
    projects: list = Field(default_factory=list)
    # Accepts both str and dict items — serialized to str by the validator below
    languages: list[LanguageItem] = Field(default_factory=list)
    work_history: list = Field(default_factory=list)
    dimension_scores: dict = Field(default_factory=dict)

    # Flag: True = l'extraction IA a déjà été effectuée pour ce candidat
    extracted: bool = False

    @field_validator("languages", mode="before")
    @classmethod
    def normalize_languages(cls, v):
        """Normalise chaque élément de 'languages' en chaîne lisible."""
        if not v:
            return []
        result = []
        for item in v:
            if isinstance(item, dict):
                result.append(LanguageEntry.from_any(item))
            else:
                result.append(str(item) if item else "")
        return result

    class Config:
        from_attributes = True
