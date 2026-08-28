import { ApiError, getDashboard } from "../api/client";
import StatTile from "../components/StatTile";
import { useAsync } from "../hooks/useAsync";
import ConnectPrompt from "./ConnectPrompt";

export default function Dashboard() {
  const { data, error, loading } = useAsync(getDashboard, []);

  if (loading) return <p className="muted">Loading…</p>;

  if (error) {
    if (error instanceof ApiError && error.status === 409) return <ConnectPrompt />;
    return <p className="muted">Couldn't load your dashboard. Try again shortly.</p>;
  }

  if (!data) return null;

  const tiles: { label: string; value: number | null; trend: (number | null)[] }[] = [
    { label: "Body battery", value: data.today.bodyBattery, trend: data.trends.bodyBattery },
    { label: "Training readiness", value: data.today.trainingReadiness, trend: data.trends.trainingReadiness },
    { label: "Sleep score", value: data.today.sleepScore, trend: data.trends.sleepScore },
    { label: "Resting heart rate", value: data.today.restingHeartRate, trend: data.trends.restingHeartRate },
    { label: "HRV", value: data.today.hrv, trend: data.trends.hrv },
  ];

  return (
    <div className="tile-grid">
      {tiles.map((tile) => (
        <StatTile key={tile.label} label={tile.label} value={tile.value} trend={tile.trend} />
      ))}
    </div>
  );
}
