"""Database tables.

For now: a Job (extracted from a pasted JD) and its Competencies. Interview sessions,
turns, and evaluations come later — when there's an interview to persist — and will hang
off Job the same way.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import ForeignKey
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


class Competency(Base):
    __tablename__ = "competencies"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    name: Mapped[str]
    description: Mapped[str]

    job: Mapped[Job] = relationship(back_populates="competencies")
