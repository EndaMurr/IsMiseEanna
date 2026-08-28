import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError, getPlanProgress } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import ConnectPrompt from "./ConnectPrompt";

const STORAGE_KEY = "ismiseeanna.raceDate";

function loadStoredRaceDate(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export default function PlanProgress() {
  const [raceDate, setRaceDate] = useState(loadStoredRaceDate);
  const [submittedDate, setSubmittedDate] = useState(raceDate);

  const { data, error, loading } = useAsync(
    submittedDate ? () => getPlanProgress(submittedDate) : null,
    [submittedDate],
  );

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    try {
      localStorage.setItem(STORAGE_KEY, raceDate);
    } catch {
      // per-viewer convenience only - fine if storage is unavailable
    }
    setSubmittedDate(raceDate);
  }

  return (
    <div>
      <form onSubmit={handleSubmit} className="race-date-form">
        <label htmlFor="race-date">Race date</label>
        <input
          id="race-date"
          type="date"
          value={raceDate}
          onChange={(event) => setRaceDate(event.target.value)}
          required
        />
        <button type="submit">Update</button>
      </form>

      {!submittedDate && <p className="muted">Enter your race date to see plan progress.</p>}

      {submittedDate && loading && <p className="muted">Loading…</p>}

      {submittedDate && Boolean(error) && (error instanceof ApiError && error.status === 409 ? (
        <ConnectPrompt />
      ) : (
        <p className="muted">Couldn't load plan progress. Try again shortly.</p>
      ))}

      {submittedDate && data && (
        <div className="card">
          <p>
            {data.daysUntilRace >= 0 ? `${data.daysUntilRace} days until race day` : "Race day has passed"}
          </p>
          {data.currentWeek !== null ? (
            <p>
              Week {data.currentWeek}
              {data.totalWeeks !== null ? ` of ${data.totalWeeks}` : ""}
              {data.matchedSessionName ? ` · ${data.matchedSessionName}` : ""}
            </p>
          ) : (
            <p className="muted">No plan week detected for this week yet.</p>
          )}
        </div>
      )}
    </div>
  );
}
