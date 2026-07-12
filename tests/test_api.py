"""API tests — real HTTP calls against the app, but with a throwaway in-memory DB and
a fake provider standing in for the LLM. No network, no rehearse.db file."""

from collections.abc import Iterator
from typing import TypeVar, cast

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from eval.schemas import CompetencyEvaluation, DimensionScore, SessionEvaluation
from finetune.schemas import FitScore
from ingestion.schemas import Competency, JobProfile
from screener.schemas import QuestionSet, RequiredSkills, ResumeProfile
from services.api.deps import get_db, get_embedder, get_provider
from services.api.main import app
from services.api.models import Base


def _fake_embedder(texts: list[str]) -> list[list[float]]:
    kws = ["python", "java", "react"]
    return [[float(t.lower().count(kw)) for kw in kws] for t in texts]

_T = TypeVar("_T", bound=BaseModel)


def _profile() -> JobProfile:
    return JobProfile(
        role_title="ML Engineer",
        seniority="Senior",
        competencies=[
            Competency(name="RAG systems", description="Builds retrieval pipelines."),
            Competency(name="Production debugging", description="Diagnoses incidents."),
            Competency(name="Communication", description="Explains ML clearly."),
        ],
    )


def _evaluation() -> SessionEvaluation:
    scores = {"relevance": 4, "depth": 2, "evidence": 2, "communication": 4}
    dims = [
        DimensionScore(dimension=d, rationale="r", score=s, evidence_quotes=["q"])  # type: ignore[arg-type]
        for d, s in scores.items()
    ]
    return SessionEvaluation(
        competency_evaluations=[
            CompetencyEvaluation(
                competency="RAG systems",
                dimension_scores=dims,
                competency_score=3.0,
                summary_feedback="solid framing, weak measurement",
            )
        ],
        overall_feedback="decent overall, work on rigor",
    )


def _fitscore() -> FitScore:
    return FitScore(
        overall_fit=78,
        skills_match=4,
        experience_match=4,
        seniority_match=5,
        matched_skills=["RAG systems", "Communication"],
        missing_skills=["Production debugging"],
        rationale="Strong on retrieval and communication, lighter on incident work.",
    )


def _resume_profile() -> ResumeProfile:
    return ResumeProfile(
        name="Jane Doe",
        summary="ML engineer with RAG experience.",
        skills=["Python", "RAG systems"],
        years_experience=6.0,
        titles=["Senior ML Engineer"],
    )


def _question_set() -> QuestionSet:
    return QuestionSet(
        questions=["Walk me through a RAG system you shipped.", "How do you debug it?"]
    )


def _required_skills() -> RequiredSkills:
    return RequiredSkills(required=["RAG systems", "Python"], nice_to_have=["Kubernetes"])


class _SchemaFake:
    """Returns a canned response based on the schema requested — so one fake can serve
    both ingestion (JobProfile) and evaluation (SessionEvaluation)."""

    model_id = "fake-provider"

    def __init__(self, responses: dict[type[BaseModel], BaseModel]) -> None:
        self._responses = responses

    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[_T],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> _T:
        return cast(_T, self._responses[schema])


@pytest.fixture
def client() -> Iterator[TestClient]:
    # StaticPool keeps the in-memory DB alive across the connections the app opens.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_db() -> Iterator[Session]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    fake = _SchemaFake(
        {
            JobProfile: _profile(),
            SessionEvaluation: _evaluation(),
            FitScore: _fitscore(),
            ResumeProfile: _resume_profile(),
            QuestionSet: _question_set(),
            RequiredSkills: _required_skills(),
        }
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_provider] = lambda: fake
    app.dependency_overrides[get_embedder] = lambda: _fake_embedder
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_job(client: TestClient) -> int:
    r = client.post("/jobs", json={"job_description": "Senior ML Engineer building RAG..."})
    assert r.status_code == 201
    return int(r.json()["id"])


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_create_then_fetch_job(client: TestClient) -> None:
    job_id = _make_job(client)
    fetched = client.get(f"/jobs/{job_id}")
    assert fetched.status_code == 200
    assert fetched.json()["role_title"] == "ML Engineer"
    assert len(fetched.json()["competencies"]) == 3
    assert len(client.get("/jobs").json()) == 1


def test_missing_job_returns_404(client: TestClient) -> None:
    assert client.get("/jobs/999").status_code == 404


def test_empty_job_description_rejected(client: TestClient) -> None:
    assert client.post("/jobs", json={"job_description": "   "}).status_code == 422


def test_session_and_evaluation_flow(client: TestClient) -> None:
    job_id = _make_job(client)

    turns = {
        "turns": [
            {"speaker": "interviewer", "text": "Tell me about a RAG system you built."},
            {"speaker": "candidate", "text": "I bumped top_k and it felt better."},
        ]
    }
    created = client.post(f"/jobs/{job_id}/sessions", json=turns)
    assert created.status_code == 201
    session_id = created.json()["id"]
    assert len(created.json()["turns"]) == 2
    assert created.json()["evaluation"] is None  # not scored yet

    scored = client.post(f"/sessions/{session_id}/evaluate")
    assert scored.status_code == 200
    body = scored.json()
    assert body["overall_feedback"] == "decent overall, work on rigor"
    assert body["competency_scores"][0]["competency"] == "RAG systems"
    assert body["competency_scores"][0]["score"] == 3.0

    fetched = client.get(f"/sessions/{session_id}")
    assert fetched.json()["evaluation"]["competency_scores"][0]["score"] == 3.0


def test_evaluate_unknown_session_404(client: TestClient) -> None:
    assert client.post("/sessions/999/evaluate").status_code == 404


def test_live_token_requires_livekit_config(client: TestClient) -> None:
    # No LiveKit env is set in tests, so the voice endpoint should 503, not crash.
    job_id = _make_job(client)
    assert client.post(f"/jobs/{job_id}/live-token").status_code == 503


def test_list_job_sessions(client: TestClient) -> None:
    job_id = _make_job(client)
    turns = {
        "turns": [
            {"speaker": "interviewer", "text": "q"},
            {"speaker": "candidate", "text": "a"},
        ]
    }
    client.post(f"/jobs/{job_id}/sessions", json=turns)
    listed = client.get(f"/jobs/{job_id}/sessions")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_session_for_unknown_job_404(client: TestClient) -> None:
    r = client.post("/jobs/999/sessions", json={"turns": [{"speaker": "x", "text": "y"}]})
    assert r.status_code == 404


def test_parse_resume_route(client: TestClient) -> None:
    r = client.post("/resume", json={"resume_text": "Jane Doe, ML engineer, Python, RAG."})
    assert r.status_code == 200
    assert "Python" in r.json()["skills"]


def test_parse_resume_empty_rejected(client: TestClient) -> None:
    assert client.post("/resume", json={"resume_text": "   "}).status_code == 422


def test_resume_upload_txt(client: TestClient) -> None:
    r = client.post(
        "/resume/upload", files={"file": ("resume.txt", b"Jane Doe, Python, RAG", "text/plain")}
    )
    assert r.status_code == 200
    assert "Jane Doe" in r.json()["resume_text"]


def test_resume_upload_empty_rejected(client: TestClient) -> None:
    r = client.post("/resume/upload", files={"file": ("resume.txt", b"   ", "text/plain")})
    assert r.status_code == 422


def test_fit_route_returns_fit_and_gap(client: TestClient) -> None:
    job_id = _make_job(client)
    r = client.post(f"/jobs/{job_id}/fit", json={"resume_text": "Jane Doe, RAG, Python."})
    assert r.status_code == 200
    body = r.json()
    assert body["fit"]["overall_fit"] == 78
    assert "Production debugging" in body["gap"]["gaps"]
    assert body["gap"]["summary"]


def test_fit_route_missing_job_404(client: TestClient) -> None:
    assert client.post("/jobs/999/fit", json={"resume_text": "x"}).status_code == 404


def test_questions_route(client: TestClient) -> None:
    job_id = _make_job(client)
    r = client.post(f"/jobs/{job_id}/questions", json={"resume_text": "Jane Doe, RAG, Python."})
    assert r.status_code == 200
    assert len(r.json()["questions"]) >= 1


def test_candidate_retrieval_ranks_pool(client: TestClient) -> None:
    # JD text (not the extracted competencies) is what's embedded, so put "python" in it.
    made = client.post("/jobs", json={"job_description": "Senior python engineer for RAG systems"})
    job_id = made.json()["id"]
    client.post("/resumes", json={"name": "Py Dev", "resume_text": "python python python"})
    client.post("/resumes", json={"name": "FE Dev", "resume_text": "react react"})

    r = client.get(f"/jobs/{job_id}/candidates?k=2")
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert names[0] == "Py Dev"  # the python resume is closest to the python-ish JD
    assert len(names) == 2


def test_add_resume_empty_rejected(client: TestClient) -> None:
    r = client.post("/resumes", json={"name": "x", "resume_text": "  "})
    assert r.status_code == 422
