// Animated circular gauge for the 0-100 fit score. Colour tracks the value.

export function ScoreGauge({ value }: { value: number }) {
  const r = 56;
  const circumference = 2 * Math.PI * r;
  const offset = circumference * (1 - Math.max(0, Math.min(100, value)) / 100);
  const color = value >= 75 ? "var(--good)" : value >= 50 ? "var(--warn)" : "var(--bad)";

  return (
    <div className="gauge">
      <svg viewBox="0 0 132 132" width="132" height="132">
        <circle className="gauge-track" cx="66" cy="66" r={r} />
        <circle
          className="gauge-fill"
          cx="66"
          cy="66"
          r={r}
          style={{ strokeDasharray: circumference, strokeDashoffset: offset, stroke: color }}
        />
      </svg>
      <div className="gauge-label">
        <span className="gauge-num" style={{ color }}>
          {value}
        </span>
        <span className="gauge-unit">/ 100 fit</span>
      </div>
    </div>
  );
}
