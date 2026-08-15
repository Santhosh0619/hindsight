import { Badge } from "@/components/ui/badge";
import { StatusPill } from "@/components/ui/status-pill";
import { Timestamp } from "@/components/ui/timestamp";
import type { AgentRunOut } from "@/lib/types";

const STATUS_TONE: Record<string, "muted" | "success" | "warning" | "destructive"> = {
  running: "warning",
  done: "success",
  error: "destructive",
};

export function RunsTable({
  runs,
  selectedRunId,
  onSelectRun,
}: {
  runs: AgentRunOut[];
  selectedRunId: string | null;
  onSelectRun: (runId: string) => void;
}): React.JSX.Element {
  if (runs.length === 0) {
    return <p className="text-sm text-muted-foreground">No agent runs yet.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted-foreground">
            <th className="pb-2 pr-4 font-medium">Incident</th>
            <th className="pb-2 pr-4 font-medium">Status</th>
            <th className="pb-2 pr-4 font-medium">Started</th>
            <th className="pb-2 pr-4 font-medium">Tokens</th>
            <th className="pb-2 font-medium">Cache</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr
              key={run.id}
              onClick={() => onSelectRun(run.id)}
              className={`cursor-pointer border-b border-border last:border-0 hover:bg-muted ${
                selectedRunId === run.id ? "bg-muted" : ""
              }`}
            >
              <td className="py-2 pr-4">{run.incident_title}</td>
              <td className="py-2 pr-4">
                <StatusPill status={run.status} tone={STATUS_TONE[run.status] ?? "muted"} />
              </td>
              <td className="py-2 pr-4">
                <Timestamp value={run.started_at} />
              </td>
              <td className="py-2 pr-4 tabular-nums">
                {run.total_tokens_in + run.total_tokens_out}
              </td>
              <td className="py-2">
                {run.from_cache ? <Badge variant="muted">cached</Badge> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
