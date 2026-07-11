"""The job-description bank and the fit levels we generate resumes for.

Same idea as eval/generate.py's JOBS: a fixed set of postings we spread the synthetic
data across. Here each posting carries the structured detail a screener needs (required
skills, seniority) so the teacher has something concrete to score against.

FIT_LEVELS describe how a generated resume should relate to a posting. Generating across
these on purpose gives the dataset a spread of scores instead of everything landing at
"great match", which a fit scorer has to handle.
"""

from __future__ import annotations

from typing import TypedDict


class JobPosting(TypedDict):
    job_id: str
    role: str
    seniority: str
    required_skills: list[str]
    nice_to_have: list[str]
    jd_text: str


# Roles and seniorities chosen to cover the space a real screener sees: ML/data/backend/
# platform/frontend, junior through senior. Keep jd_text compact to keep token cost down.
JOBS: list[JobPosting] = [
    {
        "job_id": "ml_engineer_senior",
        "role": "Senior Machine Learning Engineer",
        "seniority": "senior",
        "required_skills": ["Python", "PyTorch", "LLMs", "model serving", "AWS"],
        "nice_to_have": ["Kubernetes", "RAG", "distributed training"],
        "jd_text": (
            "Senior ML Engineer to build and ship LLM-powered features. Own models from "
            "training through serving in production, work with large datasets, and set the "
            "technical direction for a small team. 5+ years building ML systems."
        ),
    },
    {
        "job_id": "data_scientist_mid",
        "role": "Data Scientist",
        "seniority": "mid",
        "required_skills": ["Python", "SQL", "statistics", "experiment design", "A/B testing"],
        "nice_to_have": ["causal inference", "dashboarding", "scikit-learn"],
        "jd_text": (
            "Data Scientist to design and analyze experiments and turn product questions "
            "into measurable answers. Partner with product and engineering, own the analysis "
            "end to end, and communicate results clearly. 2-4 years of experience."
        ),
    },
    {
        "job_id": "backend_engineer_mid",
        "role": "Backend Engineer",
        "seniority": "mid",
        "required_skills": ["Python", "REST APIs", "PostgreSQL", "Docker", "system design"],
        "nice_to_have": ["Kafka", "gRPC", "observability"],
        "jd_text": (
            "Backend Engineer to design and operate reliable services. Build APIs, own the "
            "data model, and debug production issues. Comfortable with tradeoffs around "
            "latency, consistency, and cost. 3+ years of backend experience."
        ),
    },
    {
        "job_id": "platform_engineer_senior",
        "role": "Senior Platform / Infrastructure Engineer",
        "seniority": "senior",
        "required_skills": ["Kubernetes", "Terraform", "CI/CD", "Go or Python", "cloud (AWS/GCP)"],
        "nice_to_have": ["operators", "Helm", "service mesh", "cost optimization"],
        "jd_text": (
            "Senior Platform Engineer to own the internal compute platform: Kubernetes, "
            "infrastructure as code, and CI/CD. Build self-serve tooling for product teams "
            "and keep the platform reliable and cost-efficient. 5+ years in infra."
        ),
    },
    {
        "job_id": "data_engineer_mid",
        "role": "Data Engineer",
        "seniority": "mid",
        "required_skills": ["Python", "SQL", "Spark", "data pipelines", "Airflow"],
        "nice_to_have": ["dbt", "streaming", "data warehousing"],
        "jd_text": (
            "Data Engineer to build and maintain the pipelines that feed analytics and ML. "
            "Model data, schedule and monitor batch jobs, and keep data quality high. 3+ "
            "years building data pipelines."
        ),
    },
    {
        "job_id": "frontend_engineer_junior",
        "role": "Frontend Engineer",
        "seniority": "junior",
        "required_skills": ["JavaScript", "React", "HTML/CSS", "REST APIs"],
        "nice_to_have": ["TypeScript", "Next.js", "testing"],
        "jd_text": (
            "Frontend Engineer early in their career to build user-facing web features with "
            "React. Turn designs into responsive UI, wire up APIs, and learn quickly on a "
            "supportive team. 0-2 years of experience."
        ),
    },
    {
        "job_id": "mlops_engineer_mid",
        "role": "MLOps Engineer",
        "seniority": "mid",
        "required_skills": ["Python", "Docker", "Kubernetes", "ML pipelines", "monitoring"],
        "nice_to_have": ["MLflow", "feature stores", "model registries"],
        "jd_text": (
            "MLOps Engineer to productionize models: build training and deployment pipelines, "
            "add monitoring and rollback, and make it easy for data scientists to ship. 3+ "
            "years bridging ML and infrastructure."
        ),
    },
    {
        "job_id": "security_engineer_senior",
        "role": "Senior Security Engineer",
        "seniority": "senior",
        "required_skills": ["application security", "threat modeling", "Python", "cloud security"],
        "nice_to_have": ["SAST/DAST", "incident response", "compliance"],
        "jd_text": (
            "Senior Security Engineer to lead application and cloud security. Run threat "
            "models, review designs, build guardrails into CI/CD, and drive incident "
            "response. 5+ years in security engineering."
        ),
    },
]

# How a generated resume should relate to the posting. Descriptions are written to nudge
# the generator toward a specific score band without ever mentioning a score.
FIT_LEVELS: dict[str, str] = {
    "strong": (
        "a strong match: has most required skills with real depth, the right seniority, "
        "and concrete accomplishments in the same field"
    ),
    "partial": (
        "a partial match: hits some required skills but is clearly missing others, with "
        "shallower experience in a few areas"
    ),
    "wrong_field": (
        "a candidate from a genuinely unrelated profession (for example nursing, accounting, "
        "teaching, civil engineering, sales): experienced in their own field but with almost "
        "none of the technical skills this role needs"
    ),
    "over_senior": (
        "over-qualified: clearly more senior than the role asks for, with skills well beyond "
        "what is required, which is its own kind of mismatch"
    ),
    "under_senior": (
        "under-qualified on seniority: has the right kind of skills but far less experience "
        "than the role requires, more junior than asked for"
    ),
}
