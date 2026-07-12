"use client";

import { useState } from "react";
import { addToPool, getCandidates, type Candidate } from "@/lib/api";

// Recruiter-side view of the pgvector retrieval: add resumes to a pool, then rank the pool
// against the current job by semantic similarity.

export function CandidatePool({ jobId }: { jobId: number }) {
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function add() {
    setBusy(true);
    setMsg("");
    try {
      await addToPool(name, text);
      setMsg(`Added ${name} to the pool.`);
      setName("");
      setText("");
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function find() {
    setBusy(true);
    setMsg("");
    try {
      setCandidates(await getCandidates(jobId, 5));
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  const canAdd = name.trim().length > 0 && text.trim().length >= 40;

  return (
    <div className="panel">
      <strong>Candidate pool (recruiter view)</strong>
      <p className="muted" style={{ fontSize: 13, marginTop: 4 }}>
        Add resumes, then rank the pool against this role by meaning, not keywords (pgvector).
      </p>
      <input
        className="text-input"
        placeholder="Candidate name"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <textarea
        placeholder="Paste a candidate resume..."
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <button onClick={add} disabled={busy || !canAdd}>
        Add to pool
      </button>
      <button onClick={find} disabled={busy} style={{ marginLeft: 10 }}>
        Find top candidates
      </button>
      {msg && (
        <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>
          {msg}
        </p>
      )}
      {candidates && (
        <div style={{ marginTop: 12 }}>
          {candidates.length === 0 ? (
            <p className="muted">The pool is empty — add a few resumes first.</p>
          ) : (
            candidates.map((c) => (
              <div key={c.name} className="cand-row">
                <div style={{ flex: 1 }}>
                  <div>{c.name}</div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {c.snippet}
                  </div>
                </div>
                <div className="cand-sim">{Math.round(c.similarity * 100)}%</div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
