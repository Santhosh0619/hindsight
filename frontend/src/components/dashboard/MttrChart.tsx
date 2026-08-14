import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ValueType } from "recharts/types/component/DefaultTooltipContent";

import type { MttrPointOut } from "@/lib/types";

function formatWeek(weekStart: string): string {
  const date = new Date(weekStart);
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function MttrChart({ points }: { points: MttrPointOut[] }): React.JSX.Element {
  const hasAnyData = points.some((p) => p.mttr_minutes !== null);

  if (!hasAnyData) {
    return (
      <div className="flex h-52 items-center justify-center text-sm text-muted-foreground">
        No resolved incidents in the last 8 weeks.
      </div>
    );
  }

  const data = points.map((p) => ({
    week: formatWeek(p.week_start),
    mttr_minutes: p.mttr_minutes,
  }));

  return (
    <div className="h-52 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis dataKey="week" tick={{ fontSize: 12 }} />
          <YAxis
            tick={{ fontSize: 12 }}
            label={{ value: "minutes", angle: -90, position: "insideLeft", fontSize: 12 }}
          />
          <Tooltip
            formatter={(value: ValueType | undefined) => [
              `${Math.round(Number(value))} min`,
              "MTTR",
            ]}
          />
          <Line
            type="monotone"
            dataKey="mttr_minutes"
            stroke="var(--color-accent)"
            strokeWidth={2}
            connectNulls={false}
            dot={{ r: 3 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
