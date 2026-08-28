import { ApiError, getWeeklyCheckIn } from "../api/client";
import type { SessionItem } from "../api/client";
import TrendChart from "../components/TrendChart";
import { useAsync } from "../hooks/useAsync";
import ConnectPrompt from "./ConnectPrompt";

function SessionList({ title, items }: { title: string; items: SessionItem[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3>{title}</h3>
      <ul>
        {items.map((item) => (
          <li key={`${item.date}-${item.name ?? ""}`}>
            <span className="muted">{item.date}</span> {item.name ?? "Session"}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function WeeklyCheckIn() {
  const { data, error, loading } = useAsync(getWeeklyCheckIn, []);

  if (loading) return <p className="muted">Loading…</p>;

  if (error) {
    if (error instanceof ApiError && error.status === 409) return <ConnectPrompt />;
    return <p className="muted">Couldn't load this week's check-in. Try again shortly.</p>;
  }

  if (!data) return null;

  return (
    <div>
      <p className="muted">
        {data.weekStart} – {data.weekEnd} · {data.sessionsScheduled} scheduled
      </p>

      {(data.readinessSuppressed || data.hrvSuppressed) && (
        <div className="card">
          {data.readinessSuppressed && <p>Training readiness has been suppressed the last few days.</p>}
          {data.hrvSuppressed && <p>HRV has been suppressed the last few days.</p>}
        </div>
      )}

      <SessionList title="Missed" items={data.sessionsMissed} />
      <SessionList title="Completed" items={data.sessionsCompleted} />
      <SessionList title="Upcoming" items={data.sessionsUpcoming} />

      <div className="card">
        <div className="stat-tile-label">Training readiness</div>
        <TrendChart values={data.recoveryTrend.trainingReadiness} width={240} height={48} />
      </div>
      <div className="card">
        <div className="stat-tile-label">HRV</div>
        <TrendChart values={data.recoveryTrend.hrv} width={240} height={48} />
      </div>
    </div>
  );
}
