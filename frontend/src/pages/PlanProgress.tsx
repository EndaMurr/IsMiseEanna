import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError, getPlanProgress } from "../api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
      <form onSubmit={handleSubmit} className="mb-4 flex items-center gap-2">
        <Label htmlFor="race-date">Race date</Label>
        <Input
          id="race-date"
          type="date"
          value={raceDate}
          onChange={(event) => setRaceDate(event.target.value)}
          required
          className="w-auto"
        />
        <Button type="submit" size="sm">
          Update
        </Button>
      </form>

      {!submittedDate && <p className="text-muted-foreground text-sm">Enter your race date to see plan progress.</p>}

      {submittedDate && loading && <p className="text-muted-foreground text-sm">Loading…</p>}

      {submittedDate &&
        Boolean(error) &&
        (error instanceof ApiError && error.status === 409 ? (
          <ConnectPrompt />
        ) : (
          <p className="text-muted-foreground text-sm">Couldn't load plan progress. Try again shortly.</p>
        ))}

      {submittedDate && data && (
        <Card>
          <CardContent className="flex flex-col items-center gap-1 py-2 text-center">
            <span className="font-heading text-5xl leading-none font-semibold">
              {data.daysUntilRace >= 0 ? data.daysUntilRace : "—"}
            </span>
            <span className="text-muted-foreground text-sm">
              {data.daysUntilRace >= 0 ? "days until race day" : "Race day has passed"}
            </span>
            {data.currentWeek !== null ? (
              <span className="mt-3 text-sm">
                Week {data.currentWeek}
                {data.totalWeeks !== null ? ` of ${data.totalWeeks}` : ""}
                {data.matchedSessionName ? ` · ${data.matchedSessionName}` : ""}
              </span>
            ) : (
              <span className="text-muted-foreground mt-3 text-sm">No plan week detected for this week yet.</span>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
