"""Ingestion: schema rules + that extraction wires the JD through to the provider.
No network — a FakeProvider returns a canned profile."""

import pytest
from pydantic import ValidationError

from ingestion.extract import extract_competencies
from ingestion.schemas import Competency, JobProfile
from rehearse_core.llm.fake import FakeProvider


def _profile() -> JobProfile:
    return JobProfile(
        role_title="ML Engineer",
        seniority="Senior",
        competencies=[
            Competency(name="RAG systems", description="Builds and runs retrieval pipelines."),
            Competency(name="Production debugging", description="Diagnoses live incidents."),
            Competency(name="Communication", description="Explains ML to non-experts."),
        ],
    )


def test_profile_requires_a_few_competencies() -> None:
    with pytest.raises(ValidationError):
        JobProfile(role_title="x", competencies=[])  # too few


def test_competency_name_has_a_floor() -> None:
    with pytest.raises(ValidationError):
        Competency(name="x", description="too short a name")


def test_extract_passes_jd_through_and_returns_profile() -> None:
    provider = FakeProvider(_profile())
    profile = extract_competencies("Senior ML Engineer building RAG...", provider)
    assert profile.role_title == "ML Engineer"
    assert len(profile.competencies) == 3
    assert provider.last_user is not None and "RAG" in provider.last_user


def test_empty_jd_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        extract_competencies("   ", FakeProvider(_profile()))
