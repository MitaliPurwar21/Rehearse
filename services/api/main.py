"""The Rehearse API.

    uvicorn services.api.main:app --reload

POST a job description to /jobs and it extracts the competencies (ingestion) and stores
them. The interview + scoring endpoints come in later phases.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ingestion.extract import extract_competencies
from rehearse_core.llm.base import LLMProvider
from services.api.db import init_db
from services.api.deps import get_db, get_provider
from services.api.models import Competency, Job
from services.api.schemas import JobCreate, JobOut


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()  # create tables on startup
    yield


app = FastAPI(title="Rehearse API", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/jobs", response_model=JobOut, status_code=201)
def create_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(get_provider),
) -> Job:
    if not payload.job_description.strip():
        raise HTTPException(status_code=422, detail="job_description is empty")

    profile = extract_competencies(payload.job_description, provider)
    job = Job(
        role_title=profile.role_title,
        seniority=profile.seniority,
        job_description=payload.job_description,
        competencies=[
            Competency(name=c.name, description=c.description) for c in profile.competencies
        ],
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@app.get("/jobs", response_model=list[JobOut])
def list_jobs(db: Session = Depends(get_db)) -> list[Job]:
    return list(db.scalars(select(Job).order_by(Job.id)))


@app.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
