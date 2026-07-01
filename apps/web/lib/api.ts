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
