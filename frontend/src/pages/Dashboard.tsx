import { ApiError, getDashboard } from "../api/client";
import RecentWorkouts from "../components/RecentWorkouts";
import StatTile from "../components/StatTile";
import { BatteryIcon, GaugeIcon, MoonIcon, HeartPulseIcon, WaveIcon } from "../components/icons";
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

  const tiles: {
    label: string;
    value: number | null;
    trend: (number | null)[];
    unit?: string;
    goodDirection?: "up" | "down";
    icon: typeof BatteryIcon;
    // Fixed categorical slots (see theme.css), assigned in this same order
    // across the tiles - identity, never a magnitude or status signal.
    accentVar: string;
  }[] = [
    {
      label: "Body battery",
      value: data.today.bodyBattery,
      trend: data.trends.bodyBattery,
      unit: "%",
      icon: BatteryIcon,
      accentVar: "var(--series-1)",
    },
    {
      label: "Training readiness",
      value: data.today.trainingReadiness,
      trend: data.trends.trainingReadiness,
      icon: GaugeIcon,
      accentVar: "var(--series-2)",
    },
    {
      label: "Sleep score",
      value: data.today.sleepScore,
      trend: data.trends.sleepScore,
      icon: MoonIcon,
      accentVar: "var(--series-3)",
    },
    {
      label: "Resting heart rate",
      value: data.today.restingHeartRate,
      trend: data.trends.restingHeartRate,
      unit: "bpm",
      goodDirection: "down",
      icon: HeartPulseIcon,
      accentVar: "var(--series-4)",
    },
    {
      label: "HRV",
      value: data.today.hrv,
      trend: data.trends.hrv,
      unit: "ms",
      icon: WaveIcon,
      accentVar: "var(--series-5)",
    },
  ];

  return (
    <>
      <div className="tile-grid">
        {tiles.map((tile) => (
          <StatTile
            key={tile.label}
            label={tile.label}
            value={tile.value}
            trend={tile.trend}
            unit={tile.unit}
            goodDirection={tile.goodDirection}
            icon={tile.icon}
            accentVar={tile.accentVar}
          />
        ))}
      </div>
      <RecentWorkouts activities={data.recentActivities} />
    </>
  );
}
