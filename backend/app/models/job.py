from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, List


class ScreeningQuestions(BaseModel):
    minimum_degree: str = ""
    minimum_experience: int = 0
    required_certifications: List[str] = Field(default_factory=list)
    required_skills: List[str] = Field(default_factory=list)


class JobBase(BaseModel):
    title: str
    description: Optional[str] = None
    requirements: Optional[str] = None
    is_active: bool = True
    category: Optional[str] = None

    screening_questions: ScreeningQuestions = Field(
        default_factory=ScreeningQuestions
    )


class JobCreate(JobBase):
    pass


class JobUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    is_active: Optional[bool] = None
    category: Optional[str] = None
    screening_questions: Optional[ScreeningQuestions] = None


class JobResponse(JobBase):
    id: UUID
    created_by: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True