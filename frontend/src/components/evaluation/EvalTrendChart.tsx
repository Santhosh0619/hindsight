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

interface TrendPoint {
  id: string;
  run: string;
  recall_at_5: number | null;
  mrr: number | null;
}

// recharts types a custom dot's `payload` as `any` (it can't know our data shape) --
// this narrows it back to TrendPoint at the one point that matters, the click handler.
function ClickableDot(props: {
  cx?: number;
  cy?: number;
  payload?: TrendPoint;
  fill: string;
  onSelectRun: (runId: string) => void;
}): React.JSX.Element | null {
  const { cx, cy, payload, fill, onSelectRun } = props;
  if (cx === undefined || cy === undefined || !payload) return null;
  return (
    <circle
      cx={cx}
      cy={cy}
      r={4}
      fill={fill}
      stroke="none"
      style={{ cursor: "pointer" }}
      onClick={() => onSelectRun(payload.id)}
    />
  );
}

export function EvalTrendChart({
  runs,
  onSelectRun,
}: {
  runs: EvalRunOut[];
  onSelectRun: (runId: string) => void;
}): React.JSX.Element {
  if (runs.length === 0) {
    return (
      <div className="flex h-52 items-center justify-center text-sm text-muted-foreground">
        No evaluation runs yet -- run `make eval` to produce one.
      </div>
    );
  }

  // Oldest first, so the trend reads left-to-right chronologically.
  const data: TrendPoint[] = [...runs]
    .sort((a, b) => a.started_at.localeCompare(b.started_at))
    .map((run) => ({
      id: run.id,
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
            dot={<ClickableDot fill="var(--color-accent)" onSelectRun={onSelectRun} />}
            activeDot={<ClickableDot fill="var(--color-accent)" onSelectRun={onSelectRun} />}
          />
          <Line
            type="monotone"
            dataKey="mrr"
            name="MRR"
            stroke="var(--color-muted-foreground)"
            strokeWidth={2}
            connectNulls={false}
            dot={<ClickableDot fill="var(--color-muted-foreground)" onSelectRun={onSelectRun} />}
            activeDot={
              <ClickableDot fill="var(--color-muted-foreground)" onSelectRun={onSelectRun} />
            }
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
