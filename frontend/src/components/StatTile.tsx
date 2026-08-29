import TrendChart from "./TrendChart";

interface StatTileProps {
  label: string;
  value: number | null;
  trend?: (number | null)[];
  /** Shown beside the value when it's present, e.g. "bpm", "ms". */
  unit?: string;
  /** Which direction of change is favorable for this metric - most of these
   * are wellness scores where higher is better; resting heart rate is the
   * one that isn't. Drives the delta's color. */
  goodDirection?: "up" | "down";
}

function formatValue(value: number | null): string {
  return value === null ? "—" : Math.round(value).toString();
}

/** The most recent defined trend point *before* today, and how many days
 * back it is - the "vs a named period" comparison from the dataviz skill's
 * stat-tile contract. Today's own value is the trend's last entry (see
 * api_dashboard in web.py), so this walks backward from the point before
 * that, skipping any sync gaps. */
function findComparison(trend: (number | null)[] | undefined): { value: number; daysAgo: number } | null {
  if (!trend || trend.length < 2) return null;
  for (let i = trend.length - 2; i >= 0; i--) {
    const v = trend[i];
    if (v !== null) return { value: v, daysAgo: trend.length - 1 - i };
  }
  return null;
}

export default function StatTile({ label, value, trend, unit, goodDirection = "up" }: StatTileProps) {
  const hasTrend = trend?.some((v) => v !== null);
  const comparison = value !== null ? findComparison(trend) : null;

  let delta: { amount: number; sentiment: "good" | "bad" | "neutral"; periodLabel: string } | null = null;
  if (comparison !== null && value !== null) {
    const amount = Math.round(value) - Math.round(comparison.value);
    const sentiment: "good" | "bad" | "neutral" =
      amount === 0 ? "neutral" : (amount > 0) === (goodDirection === "up") ? "good" : "bad";
    delta = {
      amount,
      sentiment,
      periodLabel: comparison.daysAgo === 1 ? "yesterday" : `${comparison.daysAgo} days ago`,
    };
  }

  return (
    <div className="card stat-tile">
      <div className="stat-tile-label">{label}</div>
      <div className="stat-tile-value-row">
        <span className="stat-tile-value">{formatValue(value)}</span>
        {value !== null && unit && <span className="stat-tile-unit">{unit}</span>}
      </div>
      {value === null && <div className="stat-tile-empty">Not synced yet</div>}
      {delta && (
        <div className={`stat-tile-delta stat-tile-delta-${delta.sentiment}`}>
          {delta.amount === 0 ? "No change" : `${delta.amount > 0 ? "▲" : "▼"} ${Math.abs(delta.amount)}`} vs{" "}
          {delta.periodLabel}
        </div>
      )}
      {hasTrend && <TrendChart values={trend!} width={80} height={24} />}
    </div>
  );
}
