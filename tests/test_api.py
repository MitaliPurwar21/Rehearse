"""API tests — real HTTP calls against the app, but with a throwaway in-memory DB and
a FakeProvider standing in for the LLM. No network, no rehearse.db file."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ingestion.schemas import Competency, JobProfile
from rehearse_core.llm.fake import FakeProvider
from services.api.deps import get_db, get_provider
from services.api.main import app
from services.api.models import Base


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

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_provider] = lambda: FakeProvider(_profile())
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_create_then_fetch_job(client: TestClient) -> None:
    r = client.post("/jobs", json={"job_description": "Senior ML Engineer building RAG..."})
    assert r.status_code == 201
    body = r.json()
    assert body["role_title"] == "ML Engineer"
    assert body["seniority"] == "Senior"
    assert len(body["competencies"]) == 3
    job_id = body["id"]

    fetched = client.get(f"/jobs/{job_id}")
    assert fetched.status_code == 200
    assert fetched.json()["competencies"][0]["name"] == "RAG systems"

    listing = client.get("/jobs")
    assert listing.status_code == 200
    assert len(listing.json()) == 1


def test_missing_job_returns_404(client: TestClient) -> None:
    assert client.get("/jobs/999").status_code == 404


def test_empty_job_description_rejected(client: TestClient) -> None:
    assert client.post("/jobs", json={"job_description": "   "}).status_code == 422
