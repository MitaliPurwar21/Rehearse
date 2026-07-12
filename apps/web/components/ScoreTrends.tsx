"use client";

import { useEffect, useState } from "react";
import { getJobSessions, type Session } from "@/lib/api";

// A small SVG line chart of the overall score across scored attempts for a job.
// No chart library — a polyline plus points, styled to match the rest of the UI.

function overall(s: Session): number | null {
  if (!s.evaluation) return null;
  const scores = s.evaluation.competency_scores.map((c) => c.score);
  if (scores.length === 0) return null;
  return scores.reduce((a, b) => a + b, 0) / scores.length;
}

export function ScoreTrends({ jobId, refreshKey }: { jobId: number; refreshKey?: number }) {
  const [points, setPoints] = useState<number[]>([]);

  useEffect(() => {
    getJobSessions(jobId)
      .then((sessions) => {
        // API returns newest first; reverse to oldest -> newest for the trend.
        const vals = sessions
          .slice()
          .reverse()
          .map(overall)
          .filter((v): v is number => v !== null);
        setPoints(vals);
      })
      .catch(() => setPoints([]));
  }, [jobId, refreshKey]);

  if (points.length === 0) return null;

  const W = 320;
  const H = 150;
  const pad = 28;
  const maxX = Math.max(points.length - 1, 1);
  const x = (i: number) => pad + (i / maxX) * (W - pad * 2);
  const y = (v: number) => H - pad - (v / 5) * (H - pad * 2);
  const line = points.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const latest = points[points.length - 1];

  return (
    <div className="panel">
      <strong>Your progress</strong>
      <p className="muted" style={{ fontSize: 13, marginTop: 4 }}>
        Overall score across {points.length} scored {points.length === 1 ? "attempt" : "attempts"}
        {points.length > 1 && (
          <> · latest {latest.toFixed(1)}/5</>
        )}
      </p>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ marginTop: 8 }}>
        {[0, 1, 2, 3, 4, 5].map((tick) => (
          <g key={tick}>
            <line x1={pad} x2={W - pad} y1={y(tick)} y2={y(tick)} className="trend-grid" />
            <text x={pad - 8} y={y(tick) + 4} textAnchor="end" className="trend-axis">
              {tick}
            </text>
          </g>
        ))}
        {points.length > 1 && <polyline points={line} className="trend-line" />}
        {points.map((v, i) => (
          <circle key={i} cx={x(i)} cy={y(v)} r={4} className="trend-dot" />
        ))}
      </svg>
    </div>
  );
}
