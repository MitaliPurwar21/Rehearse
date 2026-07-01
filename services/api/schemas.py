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


class TurnIn(BaseModel):
    speaker: str  # "interviewer" or "candidate"
    text: str


class SessionCreate(BaseModel):
    turns: list[TurnIn]


class TurnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    speaker: str
    text: str


class CompetencyScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    competency: str
    score: float
    summary_feedback: str


class EvaluationOut(BaseModel):
    # model_id is fine as a field name; opt out of pydantic's "model_" guard.
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    overall_feedback: str
    model_id: str
    competency_scores: list[CompetencyScoreOut]


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    turns: list[TurnOut]
    evaluation: EvaluationOut | None = None


class LiveToken(BaseModel):
    """What the browser needs to join the voice room."""

    url: str    # the LiveKit server URL (wss://...)
    token: str  # a short-lived join token
    room: str   # the room name (encodes the job id for the agent)
