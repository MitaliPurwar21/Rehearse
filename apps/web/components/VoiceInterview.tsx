"use client";

import "@livekit/components-styles";
import { LiveKitRoom, RoomAudioRenderer } from "@livekit/components-react";
import { useEffect, useRef, useState } from "react";
import { getJobSessions, getLiveToken, type Evaluation } from "@/lib/api";

type Phase = "idle" | "connecting" | "live" | "scoring" | "scored" | "error";

function scoreColor(score: number): string {
  if (score >= 3.5) return "var(--good)";
  if (score <= 2) return "var(--bad)";
  return "var(--text)";
}

export function VoiceInterview({ jobId }: { jobId: number }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [creds, setCreds] = useState<{ url: string; token: string } | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [error, setError] = useState("");
  // Sessions that already existed before this interview, so polling only reacts to the new one.
  const baselineId = useRef(0);

  async function start() {
    setError("");
    setPhase("connecting");
    try {
      const existing = await getJobSessions(jobId);
      baselineId.current = existing.reduce((max, s) => Math.max(max, s.id), 0);
      const t = await getLiveToken(jobId);
      setCreds({ url: t.url, token: t.token });
      setPhase("live");
    } catch (e) {
      setError(String(e));
      setPhase("error");
    }
  }

  // The agent scores the interview when it ends (you say "I'm done"). Watch for the new
  // scored session to appear, then show it.
  useEffect(() => {
    if (phase !== "live" && phase !== "scoring") return;
    const timer = setInterval(async () => {
      try {
        const sessions = await getJobSessions(jobId);
        const done = sessions.find((s) => s.id > baselineId.current && s.evaluation);
        if (done?.evaluation) {
          setEvaluation(done.evaluation);
          setPhase("scored");
        }
      } catch {
        // transient poll error — keep trying
      }
    }, 4000);
    return () => clearInterval(timer);
  }, [phase, jobId]);

  if (phase === "scored" && evaluation) {
    return (
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
    );
  }

  return (
    <div className="panel">
      <strong>Voice interview</strong>

      {phase === "idle" && (
        <>
          <p className="muted" style={{ marginTop: 8 }}>
            Put headphones on, click start, and talk to the interviewer out loud. When you&apos;re
            finished, say <b>&ldquo;I&apos;m done&rdquo;</b> — it&apos;ll score your answers.
          </p>
          <button onClick={start}>Start voice interview</button>
        </>
      )}

      {phase === "connecting" && <p className="muted" style={{ marginTop: 8 }}>Connecting…</p>}

      {phase === "live" && creds && (
        <>
          <p className="muted" style={{ marginTop: 8 }}>
            🎙️ Live — the interviewer will greet you. Speak your answers, and say
            <b> &ldquo;I&apos;m done&rdquo;</b> to finish and get scored.
          </p>
          <LiveKitRoom
            serverUrl={creds.url}
            token={creds.token}
            connect
            audio
            video={false}
            onError={(e) => {
              setError(String(e));
              setPhase("error");
            }}
          >
            <RoomAudioRenderer />
          </LiveKitRoom>
          <button onClick={() => setPhase("scoring")}>Leave</button>
        </>
      )}

      {phase === "scoring" && (
        <p className="muted" style={{ marginTop: 8 }}>Scoring your interview…</p>
      )}

      {error && <div className="error">{error}</div>}
    </div>
  );
}
