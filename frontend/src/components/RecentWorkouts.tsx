import { Activity, Bike, Dumbbell, Footprints } from "lucide-react";
import type { ComponentType, SVGProps } from "react";
import type { ActivitySummary } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const TYPE_ICON: Record<string, ComponentType<SVGProps<SVGSVGElement>>> = {
  running: Footprints,
  cycling: Bike,
  strength_training: Dumbbell,
};

function formatDistance(meters: number | null): string | null {
  if (!meters) return null;
  return `${(meters / 1000).toFixed(1)} km`;
}

function formatDuration(seconds: number | null): string | null {
  if (!seconds) return null;
  const totalMinutes = Math.round(seconds / 60);
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  return h > 0 ? `${h}h ${m}m` : `${m} min`;
}

function formatDate(startTimeLocal: string | null): string | null {
  if (!startTimeLocal) return null;
  // "2026-08-23 09:58:40" isn't strict ISO (space instead of T) - some
  // engines parse it fine as local time regardless, but don't rely on that.
  const date = new Date(startTimeLocal.replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

export default function RecentWorkouts({ activities }: { activities: ActivitySummary[] }) {
  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle className="font-heading text-base">Recent workouts</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-1">
        {activities.length === 0 ? (
          <p className="text-muted-foreground text-sm">No recent workouts yet.</p>
        ) : (
          activities.map((activity) => {
            const Icon = (activity.type && TYPE_ICON[activity.type]) || Activity;
            const distance = formatDistance(activity.distanceMeters);
            const duration = formatDuration(activity.durationSeconds);
            return (
              <div
                key={activity.activityId ?? activity.startTimeLocal}
                className="border-border flex items-center gap-3 border-b py-2.5 last:border-0 last:pb-0"
              >
                <Icon className="text-muted-foreground size-4 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{activity.name ?? "Workout"}</p>
                  <p className="text-muted-foreground text-xs">
                    {[formatDate(activity.startTimeLocal), distance, duration].filter(Boolean).join(" · ")}
                  </p>
                </div>
                {activity.averageHR !== null && (
                  <span className="text-muted-foreground shrink-0 text-xs">{activity.averageHR} bpm</span>
                )}
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}
