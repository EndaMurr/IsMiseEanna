import { Flame } from "lucide-react";
import type { TrainingStatus } from "@/api/client";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export default function TrainingStatusCard({ status }: { status: TrainingStatus }) {
  return (
    <Card className="mb-4 gap-3">
      <CardHeader>
        <CardDescription className="flex items-center gap-1.5">
          <span className="inline-flex shrink-0" style={{ color: "var(--series-2)" }}>
            <Flame />
          </span>
          Training status
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-baseline gap-4">
        <span
          className={cn(
            "font-heading text-3xl leading-none font-semibold",
            status.label === null && "text-muted-foreground text-xl font-normal",
          )}
        >
          {status.label ?? "Not synced yet"}
        </span>
        {status.vo2Max !== null && (
          <span className="text-muted-foreground text-sm">VO2 max {Math.round(status.vo2Max)}</span>
        )}
      </CardContent>
    </Card>
  );
}
