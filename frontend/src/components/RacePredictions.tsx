import { Target } from "lucide-react";
import type { RacePredictions as RacePredictionsData } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function formatTime(totalSeconds: number): string {
  const total = Math.round(totalSeconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = h > 0 ? String(m).padStart(2, "0") : String(m);
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

const DISTANCES: { label: string; key: keyof RacePredictionsData }[] = [
  { label: "5K", key: "time5K" },
  { label: "10K", key: "time10K" },
  { label: "Half marathon", key: "timeHalfMarathon" },
  { label: "Marathon", key: "timeMarathon" },
];

/** Garmin's estimated race times based on current fitness - forward-looking,
 * unlike a personal-best (which is what actually happened). Kept visually
 * and conceptually separate: series-1 (blue) here vs. this app previously
 * used a gold/series-4 tone for actual bests, so the two ideas don't blur
 * even though only one of them currently ships. */
export default function RacePredictions({ predictions }: { predictions: RacePredictionsData }) {
  const hasAny = DISTANCES.some(({ key }) => predictions[key] !== null);
  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle className="font-heading flex items-center gap-1.5 text-base">
          <Target className="size-4 text-[var(--series-1)]" />
          Race predictions
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!hasAny ? (
          <p className="text-muted-foreground text-sm">Not enough data yet.</p>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {DISTANCES.map(({ label, key }) => {
              const seconds = predictions[key];
              return (
                <div key={key} className="flex flex-col gap-0.5">
                  <span className="text-muted-foreground text-xs">{label}</span>
                  <span className="font-heading text-lg leading-none font-semibold">
                    {seconds !== null ? formatTime(seconds) : "—"}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
