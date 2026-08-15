import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ValueType } from "recharts/types/component/DefaultTooltipContent";

import type { EvalRunOut } from "@/lib/types";

function formatRunTime(startedAt: string): string {
  const date = new Date(startedAt);
  return (
    date.toLocaleDateString(undefined, { month: "short", day: "numeric" }) +
    " " +
    date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
  );
}

export function EvalTrendChart({ runs }: { runs: EvalRunOut[] }): React.JSX.Element {
  if (runs.length === 0) {
    return (
      <div className="flex h-52 items-center justify-center text-sm text-muted-foreground">
        No evaluation runs yet -- run `make eval` to produce one.
      </div>
    );
  }

  // Oldest first, so the trend reads left-to-right chronologically.
  const data = [...runs]
    .sort((a, b) => a.started_at.localeCompare(b.started_at))
    .map((run) => ({
      run: formatRunTime(run.started_at),
      recall_at_5: run.recall_at_5,
      mrr: run.mrr,
    }));

  return (
    <div className="h-52 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis dataKey="run" tick={{ fontSize: 12 }} />
          <YAxis domain={[0, 1]} tick={{ fontSize: 12 }} />
          <Tooltip
            formatter={(value: ValueType | undefined, name: unknown) => [
              `${Math.round(Number(value) * 100)}%`,
              String(name),
            ]}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="recall_at_5"
            name="recall@5"
            stroke="var(--color-accent)"
            strokeWidth={2}
            connectNulls={false}
            dot={{ r: 3 }}
          />
          <Line
            type="monotone"
            dataKey="mrr"
            name="MRR"
            stroke="var(--color-muted-foreground)"
            strokeWidth={2}
            connectNulls={false}
            dot={{ r: 3 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
