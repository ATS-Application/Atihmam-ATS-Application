from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

# jfijfjvjgreoihgoir
class JobBase(BaseModel):
    title: str
    description: str | None = None
    requirements: str | None = None
    is_active: bool = True


class JobCreate(JobBase):
    pass


class JobUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    requirements: str | None = None
    is_active: bool | None = None


class JobResponse(JobBase):
    id: UUID
    created_by: UUID | None = None
    created_at: datetime