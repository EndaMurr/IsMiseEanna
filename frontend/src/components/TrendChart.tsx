interface Point {
  i: number;
  v: number;
}

interface TrendChartProps {
  values: (number | null)[];
  width?: number;
  height?: number;
}

/** A sparkline: the trend line in the de-emphasis (muted) hue, with a single
 * accent-colored, surface-ringed dot marking the most recent value - per the
 * dataviz skill's stat-tile contract. Gaps (missing days) break the line
 * rather than bridging over them. */
export default function TrendChart({ values, width = 80, height = 24 }: TrendChartProps) {
  const defined: Point[] = [];
  values.forEach((v, i) => {
    if (v !== null) defined.push({ i, v });
  });

  if (defined.length === 0) {
    return <svg width={width} height={height} role="img" aria-label="No trend data" />;
  }

  const min = Math.min(...defined.map((p) => p.v));
  const max = Math.max(...defined.map((p) => p.v));
  const valueRange = max - min || 1;
  const stepX = width / Math.max(values.length - 1, 1);
  const pad = 3;

  const toXY = (p: Point) => ({
    x: p.i * stepX,
    y: pad + (1 - (p.v - min) / valueRange) * (height - pad * 2),
  });

  const segments: Point[][] = [];
  let current: Point[] = [];
  for (const p of defined) {
    if (current.length && p.i !== current[current.length - 1].i + 1) {
      segments.push(current);
      current = [];
    }
    current.push(p);
  }
  if (current.length) segments.push(current);

  const last = toXY(defined[defined.length - 1]);

  return (
    <svg width={width} height={height} role="img" aria-label="7-day trend">
      {segments.map((segment, i) => (
        <polyline
          key={i}
          fill="none"
          stroke="var(--text-muted)"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
          points={segment
            .map((p) => {
              const { x, y } = toXY(p);
              return `${x},${y}`;
            })
            .join(" ")}
        />
      ))}
      <circle cx={last.x} cy={last.y} r={4} fill="var(--accent)" stroke="var(--surface-1)" strokeWidth={2} />
    </svg>
  );
}
