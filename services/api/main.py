"""The Rehearse API.

    uvicorn services.api.main:app --reload

POST a job description to /jobs and it extracts the competencies (ingestion) and stores
them. The interview + scoring endpoints come in later phases.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from livekit import api as lk
from sqlalchemy import select
from sqlalchemy.orm import Session

from eval.runner import JudgeRunner, Transcript
from finetune.jobs import JobPosting
from ingestion.extract import extract_competencies
from rehearse_core.config import get_settings
from rehearse_core.llm.base import LLMProvider
from screener.extract_skills import extract_required_skills
from screener.extract_text import extract_text
from screener.gap import gap_report
from screener.parse_resume import parse_resume
from screener.questions import generate_questions
from screener.schemas import QuestionSet, ResumeProfile
from screener.score import score_fit
from services.api.db import init_db
from services.api.deps import get_db, get_provider
from services.api.models import (
    Competency,
    CompetencyScore,
    Evaluation,
    InterviewSession,
    Job,
    Turn,
)
from services.api.schemas import (
    EvaluationOut,
    FitOut,
    JobCreate,
    JobOut,
    LiveToken,
    ResumeIn,
    SessionCreate,
    SessionOut,
)


def _posting(job: Job, required_skills: list[str], nice_to_have: list[str]) -> JobPosting:
    """Map a stored Job into the shape the fit scorer was trained on.

    Callers pass the skills to score against, so the same prompt works whether the scorer is
    Claude or the fine-tuned model, and gaps can be as granular as the caller wants.
    """
    return {
        "job_id": str(job.id),
        "role": job.role_title,
        "seniority": job.seniority or "unspecified",
        "required_skills": required_skills,
        "nice_to_have": nice_to_have,
        "jd_text": job.job_description,
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()  # create tables on startup
    yield


app = FastAPI(title="Rehearse API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.post("/resume", response_model=ResumeProfile)
def parse_resume_route(
    payload: ResumeIn,
    provider: LLMProvider = Depends(get_provider),
) -> ResumeProfile:
    if not payload.resume_text.strip():
        raise HTTPException(status_code=422, detail="resume_text is empty")
    return parse_resume(payload.resume_text, provider)


@app.post("/resume/upload")
async def upload_resume(file: UploadFile = File(...)) -> dict[str, str]:
    """Extract text from an uploaded PDF/Word resume so the browser can prefill it."""
    data = await file.read()
    text = extract_text(file.filename or "", data)
    if not text.strip():
        raise HTTPException(status_code=422, detail="could not read any text from that file")
    return {"resume_text": text}


@app.post("/jobs/{job_id}/fit", response_model=FitOut)
def score_fit_route(
    job_id: int,
    payload: ResumeIn,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(get_provider),
) -> FitOut:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if not payload.resume_text.strip():
        raise HTTPException(status_code=422, detail="resume_text is empty")
    # Score against granular JD skills so the gaps are specific, not high-level themes.
    skills = extract_required_skills(job.job_description, provider)
    posting = _posting(job, skills.required, skills.nice_to_have)
    fit = score_fit(payload.resume_text, posting, provider)
    return FitOut(fit=fit, gap=gap_report(fit))


@app.post("/jobs/{job_id}/questions", response_model=QuestionSet)
def questions_route(
    job_id: int,
    payload: ResumeIn,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(get_provider),
) -> QuestionSet:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if not payload.resume_text.strip():
        raise HTTPException(status_code=422, detail="resume_text is empty")
    posting = _posting(job, [c.name for c in job.competencies], [])
    return generate_questions(payload.resume_text, posting, provider)


@app.post("/jobs/{job_id}/live-token", response_model=LiveToken)
def live_token(job_id: int, db: Session = Depends(get_db)) -> LiveToken:
    """Mint a token the browser uses to join a voice room for this job.

    The room name encodes the job id so the agent knows which competencies to probe.
    """
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    settings = get_settings()
    if not (settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret):
        raise HTTPException(status_code=503, detail="voice interview is not configured")

    room = f"rehearse-{job_id}-{uuid.uuid4().hex[:8]}"
    token = (
        lk.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(f"candidate-{uuid.uuid4().hex[:6]}")
        .with_grants(lk.VideoGrants(room_join=True, room=room))
        .to_jwt()
    )
    return LiveToken(url=settings.livekit_url, token=token, room=room)


@app.get("/jobs/{job_id}/sessions", response_model=list[SessionOut])
def list_job_sessions(job_id: int, db: Session = Depends(get_db)) -> list[InterviewSession]:
    """All sessions for a job, newest first — the site polls this after a voice
    interview to pick up the scored result."""
    if db.get(Job, job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    stmt = select(InterviewSession).where(InterviewSession.job_id == job_id)
    return list(db.scalars(stmt.order_by(InterviewSession.id.desc())))


@app.post("/jobs/{job_id}/sessions", response_model=SessionOut, status_code=201)
def create_session(
    job_id: int, payload: SessionCreate, db: Session = Depends(get_db)
) -> InterviewSession:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if not payload.turns:
        raise HTTPException(status_code=422, detail="transcript has no turns")

    session = InterviewSession(
        job_id=job_id,
        turns=[Turn(idx=i, speaker=t.speaker, text=t.text) for i, t in enumerate(payload.turns)],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@app.post("/sessions/{session_id}/evaluate", response_model=EvaluationOut)
def evaluate_session(
    session_id: int,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(get_provider),
) -> Evaluation:
    session = db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session.evaluation is not None:
        return session.evaluation  # already scored — don't re-charge the model

    job = session.job
    transcript = Transcript(
        job_description=job.job_description,
        competencies=[c.name for c in job.competencies],
        turns=[(t.speaker, t.text) for t in session.turns],
    )
    settings = get_settings()
    runner = JudgeRunner(
        provider, temperature=settings.judge_temperature, max_tokens=settings.judge_max_tokens
    )
    result = runner.judge(transcript)
    assert result.model_meta is not None  # the runner always stamps it

    evaluation = Evaluation(
        session_id=session.id,
        overall_feedback=result.overall_feedback,
        model_id=result.model_meta.model_id,
        prompt_hash=result.model_meta.prompt_hash,
        raw_json=result.model_dump_json(),
        competency_scores=[
            CompetencyScore(
                competency=ce.competency,
                score=ce.competency_score,
                summary_feedback=ce.summary_feedback,
            )
            for ce in result.competency_evaluations
        ],
    )
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)
    return evaluation


@app.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: int, db: Session = Depends(get_db)) -> InterviewSession:
    session = db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session
