// Thin client for the Rehearse API. The backend does the real work; this just calls it.

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Competency = { name: string; description: string };
export type Job = {
  id: number;
  role_title: string;
  seniority: string | null;
  competencies: Competency[];
};
export type CompetencyScore = {
  competency: string;
  score: number;
  summary_feedback: string;
};
export type Evaluation = {
  overall_feedback: string;
  model_id: string;
  competency_scores: CompetencyScore[];
};
export type Turn = { speaker: string; text: string };

async function send<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export function createJob(jobDescription: string): Promise<Job> {
  return send<Job>("/jobs", { job_description: jobDescription });
}

export function createSession(jobId: number, turns: Turn[]): Promise<{ id: number }> {
  return send<{ id: number }>(`/jobs/${jobId}/sessions`, { turns });
}

export function evaluateSession(sessionId: number): Promise<Evaluation> {
  return send<Evaluation>(`/sessions/${sessionId}/evaluate`);
}

export type LiveToken = { url: string; token: string; room: string };
export type Session = { id: number; job_id: number; evaluation: Evaluation | null };

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export function getLiveToken(jobId: number): Promise<LiveToken> {
  return send<LiveToken>(`/jobs/${jobId}/live-token`);
}

export function getJobSessions(jobId: number): Promise<Session[]> {
  return getJson<Session[]>(`/jobs/${jobId}/sessions`);
}

// --- resume screener (fit + gap + tailored questions) ---
export type FitScore = {
  overall_fit: number;
  skills_match: number;
  experience_match: number;
  seniority_match: number;
  matched_skills: string[];
  missing_skills: string[];
  rationale: string;
};
export type GapReport = {
  overall_fit: number;
  strengths: string[];
  gaps: string[];
  summary: string;
};
export type FitResult = { fit: FitScore; gap: GapReport };
export type QuestionSet = { questions: string[] };

export function scoreFit(jobId: number, resumeText: string): Promise<FitResult> {
  return send<FitResult>(`/jobs/${jobId}/fit`, { resume_text: resumeText });
}

export function getQuestions(jobId: number, resumeText: string): Promise<QuestionSet> {
  return send<QuestionSet>(`/jobs/${jobId}/questions`, { resume_text: resumeText });
}

export async function uploadResume(file: File): Promise<{ resume_text: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API}/resume/upload`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json() as Promise<{ resume_text: string }>;
}

// --- recruiter side: semantic candidate pool (pgvector) ---
export type Candidate = { name: string; similarity: number; snippet: string };

export function addToPool(name: string, resumeText: string): Promise<{ id: number; name: string }> {
  return send<{ id: number; name: string }>("/resumes", { name, resume_text: resumeText });
}

export function getCandidates(jobId: number, k = 5): Promise<Candidate[]> {
  return getJson<Candidate[]>(`/jobs/${jobId}/candidates?k=${k}`);
}
