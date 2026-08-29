import { AlertTriangle, CheckCircle2, Clock, XCircle } from "lucide-react";
import type { ComponentType, SVGProps } from "react";
import { ApiError, getWeeklyCheckIn } from "../api/client";
import type { SessionItem } from "../api/client";
import { GaugeIcon, WaveIcon } from "../components/icons";
import TrendCard from "../components/TrendCard";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useAsync } from "../hooks/useAsync";
import ConnectPrompt from "./ConnectPrompt";

type SessionStatus = "missed" | "completed" | "upcoming";

const STATUS: Record<
  SessionStatus,
  { label: string; icon: ComponentType<SVGProps<SVGSVGElement>>; colorClass: string }
> = {
  missed: { label: "Missed", icon: XCircle, colorClass: "text-[var(--critical)]" },
  completed: { label: "Completed", icon: CheckCircle2, colorClass: "text-[var(--delta-good)]" },
  upcoming: { label: "Upcoming", icon: Clock, colorClass: "text-muted-foreground" },
};

function SessionRow({ item, status }: { item: SessionItem; status: SessionStatus }) {
  const { label, icon: Icon, colorClass } = STATUS[status];
  return (
    <div className="border-border flex items-center gap-3 border-b py-2.5 last:border-0 last:pb-0">
      <Icon className={cn("size-4 shrink-0", colorClass)} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{item.name ?? "Session"}</p>
        <p className="text-muted-foreground text-xs">{item.date}</p>
      </div>
      <Badge variant="outline" className={cn("shrink-0 font-normal", colorClass)}>
        {label}
      </Badge>
    </div>
  );
}

export default function WeeklyCheckIn() {
  const { data, error, loading } = useAsync(getWeeklyCheckIn, []);

  if (loading) return <p className="text-muted-foreground text-sm">Loading…</p>;

  if (error) {
    if (error instanceof ApiError && error.status === 409) return <ConnectPrompt />;
    return <p className="text-muted-foreground text-sm">Couldn't load this week's check-in. Try again shortly.</p>;
  }

  if (!data) return null;

  const sessions = [
    ...data.sessionsMissed.map((item) => ({ item, status: "missed" as const })),
    ...data.sessionsCompleted.map((item) => ({ item, status: "completed" as const })),
    ...data.sessionsUpcoming.map((item) => ({ item, status: "upcoming" as const })),
  ].sort((a, b) => a.item.date.localeCompare(b.item.date));

  return (
    <div>
      <p className="text-muted-foreground mb-4 text-sm">
        {data.weekStart} – {data.weekEnd} · {data.sessionsScheduled} scheduled
      </p>

      {(data.readinessSuppressed || data.hrvSuppressed) && (
        <Card className="mb-4">
          <CardContent className="flex items-start gap-2.5">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-[var(--warning)]" />
            <div className="flex flex-col gap-1 text-sm">
              {data.readinessSuppressed && <p>Training readiness has been suppressed the last few days.</p>}
              {data.hrvSuppressed && <p>HRV has been suppressed the last few days.</p>}
            </div>
          </CardContent>
        </Card>
      )}

      <Card className="mb-4">
        <CardHeader>
          <CardTitle className="font-heading text-base">This week's sessions</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-1">
          {sessions.length === 0 ? (
            <CardDescription>No sessions scheduled this week.</CardDescription>
          ) : (
            sessions.map(({ item, status }) => (
              <SessionRow key={`${item.date}-${item.name ?? ""}`} item={item} status={status} />
            ))
          )}
        </CardContent>
      </Card>

      <TrendCard
        label="Training readiness"
        values={data.recoveryTrend.trainingReadiness}
        icon={GaugeIcon}
        accentVar="var(--series-2)"
      />
      <TrendCard label="HRV" values={data.recoveryTrend.hrv} icon={WaveIcon} accentVar="var(--series-5)" />
    </div>
  );
}
