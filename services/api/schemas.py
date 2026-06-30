"""Request/response shapes for the API (separate from the DB models on purpose).

These are what the HTTP layer speaks. from_attributes lets us return ORM objects
directly and have them serialized by these.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class JobCreate(BaseModel):
    job_description: str


class CompetencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    description: str


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role_title: str
    seniority: str | None
    competencies: list[CompetencyOut]
