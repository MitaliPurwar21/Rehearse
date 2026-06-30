"""Database tables.

The chain mirrors the product: a Job (from a pasted JD) has Competencies; an
InterviewSession under a Job has Turns; evaluating a session produces one Evaluation
with a CompetencyScore per competency. The full judge output is also kept as JSON so
nothing is lost beyond the queryable summary.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    role_title: Mapped[str]
    seniority: Mapped[str | None]
    job_description: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    competencies: Mapped[list[Competency]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[InterviewSession]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class Competency(Base):
    __tablename__ = "competencies"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    name: Mapped[str]
    description: Mapped[str]

    job: Mapped[Job] = relationship(back_populates="competencies")


class InterviewSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    job: Mapped[Job] = relationship(back_populates="sessions")
    turns: Mapped[list[Turn]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="Turn.idx"
    )
    evaluation: Mapped[Evaluation | None] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"))
    idx: Mapped[int]  # turn order within the session
    speaker: Mapped[str]
    text: Mapped[str] = mapped_column(Text)

    session: Mapped[InterviewSession] = relationship(back_populates="turns")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), unique=True)
    overall_feedback: Mapped[str] = mapped_column(Text)
    model_id: Mapped[str]
    prompt_hash: Mapped[str]
    raw_json: Mapped[str] = mapped_column(Text)  # the full judge output, for fidelity
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    session: Mapped[InterviewSession] = relationship(back_populates="evaluation")
    competency_scores: Mapped[list[CompetencyScore]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )


class CompetencyScore(Base):
    __tablename__ = "competency_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"))
    competency: Mapped[str]
    score: Mapped[float]
    summary_feedback: Mapped[str] = mapped_column(Text)

    evaluation: Mapped[Evaluation] = relationship(back_populates="competency_scores")
