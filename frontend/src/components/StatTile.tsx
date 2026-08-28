import TrendChart from "./TrendChart";

interface StatTileProps {
  label: string;
  value: number | null;
  trend?: (number | null)[];
}

function formatValue(value: number | null): string {
  return value === null ? "—" : Math.round(value).toString();
}

export default function StatTile({ label, value, trend }: StatTileProps) {
  const hasTrend = trend?.some((v) => v !== null);

  return (
    <div className="card stat-tile">
      <div className="stat-tile-label">{label}</div>
      <div className="stat-tile-value">{formatValue(value)}</div>
      {hasTrend && <TrendChart values={trend!} width={80} height={24} />}
    </div>
  );
}
