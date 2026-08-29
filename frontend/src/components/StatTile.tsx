import type { ComponentType, SVGProps } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import TrendChart from "./TrendChart";

export interface StatDelta {
  amount: number;
  sentiment: "good" | "bad" | "neutral";
  /** e.g. "yesterday", "last week" - whatever period this amount is relative to. */
  periodLabel: string;
}

interface StatTileProps {
  label: string;
  value: number | null;
  trend?: (number | null)[];
  /** Shown beside the value when it's present, e.g. "bpm", "ms". */
  unit?: string;
  /** Which direction of change is favorable for this metric - most of these
   * are wellness scores where higher is better; resting heart rate is the
   * one that isn't. Drives the delta's color. Ignored when `delta` is
   * given explicitly, since the caller has already decided the sentiment. */
  goodDirection?: "up" | "down";
  /** Pre-computed delta, for tiles with no day-by-day trend to derive one
   * from (e.g. this-week-vs-last-week totals). When omitted, the delta is
   * derived from `trend` as usual (vs the most recent prior day). */
  delta?: StatDelta | null;
  /** A fixed per-metric identity icon + color (a categorical palette slot,
   * assigned in order - never reused as a magnitude or status signal).
   * Always paired with the label text beside it, so identity never rides
   * on color/icon alone. */
  icon?: ComponentType<SVGProps<SVGSVGElement>>;
  accentVar?: string;
}

function formatValue(value: number | null): string {
  return value === null ? "—" : Math.round(value).toString();
}

/** The most recent defined trend point *before* today, and how many days
 * back it is - the "vs a named period" comparison from the dataviz skill's
 * stat-tile contract. Today's own value is the trend's last entry (see
 * api_dashboard in web.py), so this walks backward from the point before
 * that, skipping any sync gaps. */
function findComparison(trend: (number | null)[] | undefined): { value: number; daysAgo: number } | null {
  if (!trend || trend.length < 2) return null;
  for (let i = trend.length - 2; i >= 0; i--) {
    const v = trend[i];
    if (v !== null) return { value: v, daysAgo: trend.length - 1 - i };
  }
  return null;
}

export default function StatTile({
  label,
  value,
  trend,
  unit,
  goodDirection = "up",
  delta: deltaOverride,
  icon: Icon,
  accentVar,
}: StatTileProps) {
  const hasTrend = trend?.some((v) => v !== null);

  let delta: StatDelta | null = deltaOverride ?? null;
  if (deltaOverride === undefined) {
    const comparison = value !== null ? findComparison(trend) : null;
    if (comparison !== null && value !== null) {
      const amount = Math.round(value) - Math.round(comparison.value);
      const sentiment: "good" | "bad" | "neutral" =
        amount === 0 ? "neutral" : (amount > 0) === (goodDirection === "up") ? "good" : "bad";
      delta = {
        amount,
        sentiment,
        periodLabel: comparison.daysAgo === 1 ? "yesterday" : `${comparison.daysAgo} days ago`,
      };
    }
  }

  return (
    <Card className="gap-3">
      <CardHeader>
        <CardDescription className="flex items-center gap-1.5">
          {Icon && (
            <span className="inline-flex shrink-0" style={accentVar ? { color: accentVar } : undefined}>
              <Icon />
            </span>
          )}
          {label}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <div className="flex items-baseline gap-1">
          <span
            className={cn(
              "font-heading text-3xl leading-none font-semibold",
              value === null && "text-muted-foreground font-normal",
            )}
          >
            {formatValue(value)}
          </span>
          {value !== null && unit && <span className="text-muted-foreground text-sm">{unit}</span>}
        </div>
        {value === null && <p className="text-muted-foreground text-xs">Not synced yet</p>}
        {delta && (
          <Badge
            variant="outline"
            className={cn(
              "w-fit font-normal",
              delta.sentiment === "good" && "text-[var(--delta-good)]",
              delta.sentiment === "bad" && "text-[var(--critical)]",
              delta.sentiment === "neutral" && "text-muted-foreground",
            )}
          >
            {delta.amount === 0 ? "No change" : `${delta.amount > 0 ? "▲" : "▼"} ${Math.abs(delta.amount)}`} vs{" "}
            {delta.periodLabel}
          </Badge>
        )}
        {hasTrend && <TrendChart values={trend!} width={80} height={24} />}
      </CardContent>
    </Card>
  );
}
