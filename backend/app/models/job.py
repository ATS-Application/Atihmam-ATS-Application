from pydantic import BaseModel, Field, model_validator
from uuid import UUID
from datetime import datetime
from typing import Optional, List, Any


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
    domain: Optional[str] = None

    screening_questions: ScreeningQuestions = Field(
        default_factory=ScreeningQuestions
    )

    @model_validator(mode="before")
    @classmethod
    def sync_category_and_domain(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Sync domain to category for DB writes
            if "domain" in data and data.get("domain") and not data.get("category"):
                data["category"] = data["domain"]
            # Sync category to domain for API reads/writes
            elif "category" in data and data.get("category") and not data.get("domain"):
                data["domain"] = data["category"]
        return data


class JobCreate(JobBase):
    pass


class JobUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    is_active: Optional[bool] = None
    category: Optional[str] = None
    domain: Optional[str] = None
    screening_questions: Optional[ScreeningQuestions] = None

    @model_validator(mode="before")
    @classmethod
    def sync_category_and_domain_update(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "domain" in data and data.get("domain") and not data.get("category"):
                data["category"] = data["domain"]
            elif "category" in data and data.get("category") and not data.get("domain"):
                data["domain"] = data["category"]
        return data
    

class JobResponse(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    requirements: str | None = None
    is_active: bool
    created_by: UUID | None = None
    created_at: datetime
    category: str | None = None
    domain: str | None = None
    screening_questions: dict = {}
    candidate_count: int = 0       

    class Config:
        from_attributes = True