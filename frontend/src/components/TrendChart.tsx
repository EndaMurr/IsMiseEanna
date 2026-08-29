import { useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";

interface Point {
  i: number;
  v: number;
}

interface TrendChartProps {
  values: (number | null)[];
  width?: number;
  height?: number;
}

/** "Today", "Yesterday", "N days ago" - the trend is always a fixed trailing
 * window ending today (see _n_day_trend in garmin_client.py), so position in
 * the array maps directly to a relative day without needing real dates from
 * the API. */
function dayLabel(daysAgo: number): string {
  if (daysAgo === 0) return "Today";
  if (daysAgo === 1) return "Yesterday";
  return `${daysAgo} days ago`;
}

/** A sparkline: the trend line in the de-emphasis (muted) hue, with a single
 * accent-colored, surface-ringed dot marking the most recent value - per the
 * dataviz skill's stat-tile contract. Gaps (missing days) break the line
 * rather than bridging over them. It's a real plotted line, not a bare stat
 * tile, so per the skill's interaction contract it carries a hover/focus
 * crosshair + tooltip rather than being decoration-only. */
export default function TrendChart({ values, width = 80, height = 24 }: TrendChartProps) {
  const [hoverI, setHoverI] = useState<number | null>(null);

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

  const lastIndex = defined[defined.length - 1].i;
  const last = toXY(defined[defined.length - 1]);
  const hoverPoint = hoverI !== null ? defined.find((p) => p.i === hoverI) : undefined;

  function nearestDefinedIndex(clientX: number, svg: SVGSVGElement): number {
    const rect = svg.getBoundingClientRect();
    const relX = ((clientX - rect.left) / rect.width) * width;
    let best = defined[0].i;
    let bestDist = Infinity;
    for (const p of defined) {
      const dist = Math.abs(toXY(p).x - relX);
      if (dist < bestDist) {
        bestDist = dist;
        best = p.i;
      }
    }
    return best;
  }

  function handlePointerMove(e: PointerEvent<SVGSVGElement>) {
    setHoverI(nearestDefinedIndex(e.clientX, e.currentTarget));
  }

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const order = defined.map((p) => p.i);
    const current = hoverI ?? lastIndex;
    const pos = order.indexOf(current);
    if (e.key === "ArrowLeft" && pos > 0) {
      setHoverI(order[pos - 1]);
      e.preventDefault();
    } else if (e.key === "ArrowRight" && pos < order.length - 1) {
      setHoverI(order[pos + 1]);
      e.preventDefault();
    } else if (e.key === "Escape") {
      setHoverI(null);
    }
  }

  return (
    <div
      className="trend-chart-wrap"
      tabIndex={0}
      role="group"
      aria-label="7-day trend, use arrow keys to inspect each day"
      onKeyDown={handleKeyDown}
      onFocus={() => setHoverI(lastIndex)}
      onBlur={() => setHoverI(null)}
    >
      <svg
        width={width}
        height={height}
        role="img"
        aria-label="7-day trend"
        onPointerMove={handlePointerMove}
        onPointerLeave={() => setHoverI(null)}
      >
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
        {hoverPoint && (
          <line
            x1={toXY(hoverPoint).x}
            y1={0}
            x2={toXY(hoverPoint).x}
            y2={height}
            stroke="var(--baseline)"
            strokeWidth={1}
          />
        )}
        {(hoverI === null || hoverI !== lastIndex) && (
          <circle cx={last.x} cy={last.y} r={4} fill="var(--accent)" stroke="var(--surface-1)" strokeWidth={2} />
        )}
        {hoverPoint && (
          <circle
            cx={toXY(hoverPoint).x}
            cy={toXY(hoverPoint).y}
            r={4}
            fill="var(--accent)"
            stroke="var(--surface-1)"
            strokeWidth={2}
          />
        )}
      </svg>
      {hoverPoint && (
        <div className="trend-tooltip" style={{ left: `${toXY(hoverPoint).x}px` }}>
          <strong>{Math.round(hoverPoint.v)}</strong> · {dayLabel(values.length - 1 - hoverPoint.i)}
        </div>
      )}
    </div>
  );
}
