import type { ComponentType, SVGProps } from "react";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import TrendChart from "./TrendChart";

interface TrendCardProps {
  label: string;
  values: (number | null)[];
  icon?: ComponentType<SVGProps<SVGSVGElement>>;
  accentVar?: string;
}

/** A card for a recovery trend with no single headline number to lead with
 * (unlike StatTile) - just the label and a larger sparkline. Shares the
 * same icon+identity-color convention as the stat tiles. */
export default function TrendCard({ label, values, icon: Icon, accentVar }: TrendCardProps) {
  const hasData = values.some((v) => v !== null);
  return (
    <Card className="mb-4 gap-3">
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
      <CardContent>
        {hasData ? (
          <TrendChart values={values} width={240} height={48} />
        ) : (
          <p className="text-muted-foreground text-xs">Not synced yet</p>
        )}
      </CardContent>
    </Card>
  );
}
