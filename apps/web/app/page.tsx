"use client";

import { useState } from "react";
import {
  createJob,
  createSession,
  evaluateSession,
  scoreFit,
  getQuestions,
  type Evaluation,
  type FitResult,
  type Job,
} from "@/lib/api";
import { VoiceInterview } from "@/components/VoiceInterview";

const QUESTION = "Walk me through your most relevant project for this role — what you built, the hardest problem, and how you measured success.";

type Mode = "voice" | "type" | null;

function scoreColor(score: number): string {
  if (score >= 3.5) return "var(--good)";
  if (score <= 2) return "var(--bad)";
  return "var(--text)";
}

export default function Home() {
  const [jd, setJd] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [mode, setMode] = useState<Mode>(null);
  const [answer, setAnswer] = useState("");
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [resume, setResume] = useState("");
  const [fit, setFit] = useState<FitResult | null>(null);
  const [questions, setQuestions] = useState<string[] | null>(null);
  const [fitLoading, setFitLoading] = useState(false);

  async function onExtract() {
    setError("");
    setLoading(true);
    try {
      setJob(await createJob(jd));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function onCheckFit() {
    if (!job) return;
    setError("");
    setFitLoading(true);
    try {
      const [f, q] = await Promise.all([
        scoreFit(job.id, resume),
        getQuestions(job.id, resume),
      ]);
      setFit(f);
      setQuestions(q.questions);
    } catch (e) {
      setError(String(e));
    } finally {
      setFitLoading(false);
    }
  }

  async function onScore() {
    if (!job) return;
    setError("");
    setLoading(true);
    try {
      const session = await createSession(job.id, [
        { speaker: "interviewer", text: QUESTION },
        { speaker: "candidate", text: answer },
      ]);
      setEvaluation(await evaluateSession(session.id));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <h1>Rehearse</h1>
      <p className="muted">Paste a job description, do a mock interview, get scored by a calibrated AI judge.</p>

      {!job && (
        <div className="panel">
          <strong>1. Paste a job description</strong>
          <textarea
            value={jd}
            onChange={(e) => setJd(e.target.value)}
            placeholder="Paste the full job description here..."
          />
          <button onClick={onExtract} disabled={loading || jd.trim().length < 20}>
            {loading ? "Extracting..." : "Extract competencies"}
          </button>
        </div>
      )}

      {job && (
        <div className="panel">
          <strong>{job.seniority ? `${job.seniority} ` : ""}{job.role_title}</strong>
          <div style={{ marginTop: 8 }}>
            {job.competencies.map((c) => (
              <span key={c.name} className="chip" title={c.description}>
                {c.name}
              </span>
            ))}
          </div>
        </div>
      )}

      {job && (
        <div className="panel">
          <strong>Check your resume against this role</strong>
          <textarea
            value={resume}
            onChange={(e) => setResume(e.target.value)}
            placeholder="Paste your resume here..."
          />
          <button onClick={onCheckFit} disabled={fitLoading || resume.trim().length < 40}>
            {fitLoading ? "Checking..." : "Check fit"}
          </button>

          {fit && (
            <div style={{ marginTop: 16 }}>
              <div className="score-row">
                <div>Overall fit</div>
                <div className="score">{fit.fit.overall_fit}/100</div>
              </div>
              <p style={{ marginTop: 8 }}>{fit.gap.summary}</p>

              <div className="muted" style={{ fontSize: 13, marginTop: 12 }}>Strengths</div>
              <div>
                {fit.gap.strengths.length ? (
                  fit.gap.strengths.map((s) => (
                    <span key={s} className="chip">{s}</span>
                  ))
                ) : (
                  <span className="muted">none found</span>
                )}
              </div>

              <div className="muted" style={{ fontSize: 13, marginTop: 12 }}>Gaps</div>
              <div>
                {fit.gap.gaps.length ? (
                  fit.gap.gaps.map((g) => (
                    <span key={g} className="chip">{g}</span>
                  ))
                ) : (
                  <span className="muted">none</span>
                )}
              </div>

              {questions && questions.length > 0 && (
                <>
                  <div className="muted" style={{ fontSize: 13, marginTop: 16 }}>
                    Interview questions tailored to you
                  </div>
                  <ol style={{ marginTop: 6, paddingLeft: 20 }}>
                    {questions.map((q, i) => (
                      <li key={i} style={{ marginTop: 6 }}>{q}</li>
                    ))}
                  </ol>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {job && !mode && (
        <div className="panel">
          <strong>2. How do you want to practice?</strong>
          <div style={{ marginTop: 12, display: "flex", gap: 12 }}>
            <button onClick={() => setMode("voice")}>🎙️ Voice interview</button>
            <button onClick={() => setMode("type")}>⌨️ Type an answer</button>
          </div>
        </div>
      )}

      {job && mode === "voice" && <VoiceInterview jobId={job.id} />}

      {job && mode === "type" && !evaluation && (
        <div className="panel">
          <strong>Answer the question</strong>
          <p className="muted" style={{ marginTop: 8 }}>{QUESTION}</p>
          <textarea
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            placeholder="Type your answer as you would say it in an interview..."
          />
          <button onClick={onScore} disabled={loading || answer.trim().length < 20}>
            {loading ? "Scoring..." : "Get scored"}
          </button>
        </div>
      )}

      {evaluation && (
        <div className="panel">
          <strong>Your scores</strong>
          <div style={{ marginTop: 8 }}>
            {evaluation.competency_scores.map((cs) => (
              <div key={cs.competency} className="score-row">
                <div>
                  <div>{cs.competency}</div>
                  <div className="muted" style={{ fontSize: 13 }}>{cs.summary_feedback}</div>
                </div>
                <div className="score" style={{ color: scoreColor(cs.score) }}>{cs.score.toFixed(1)}</div>
              </div>
            ))}
          </div>
          <p style={{ marginTop: 16 }}>{evaluation.overall_feedback}</p>
          <p className="muted" style={{ fontSize: 12 }}>Scored by {evaluation.model_id}</p>
        </div>
      )}

      {error && <div className="error">{error}</div>}
    </main>
  );
}
