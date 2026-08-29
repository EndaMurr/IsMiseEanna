import { Trophy } from "lucide-react";
import type { PersonalRecord } from "@/api/client";
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

function formatDistance(meters: number): string {
  return `${(meters / 1000).toFixed(1)} km`;
}

function formatValue(record: PersonalRecord): string {
  return record.kind === "time" ? formatTime(record.value) : formatDistance(record.value);
}

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export default function PersonalRecords({ records }: { records: PersonalRecord[] }) {
  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle className="font-heading flex items-center gap-1.5 text-base">
          <Trophy className="size-4 text-[var(--series-4)]" />
          Personal records
        </CardTitle>
      </CardHeader>
      <CardContent>
        {records.length === 0 ? (
          <p className="text-muted-foreground text-sm">No personal records yet.</p>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            {records.map((record) => (
              <div key={record.label} className="flex flex-col gap-0.5">
                <span className="text-muted-foreground text-xs">{record.label}</span>
                <span className="font-heading text-lg leading-none font-semibold">{formatValue(record)}</span>
                {record.date && <span className="text-muted-foreground text-xs">{formatDate(record.date)}</span>}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
