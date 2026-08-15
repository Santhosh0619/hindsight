import { Badge } from "@/components/ui/badge";
import { StatusPill } from "@/components/ui/status-pill";
import type { AgentRunDetailOut } from "@/lib/types";

function formatSummaryValue(value: unknown): string {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  return String(value);
}

export function RunWaterfall({ run }: { run: AgentRunDetailOut | null }): React.JSX.Element {
  if (run === null) {
    return (
      <p className="text-sm text-muted-foreground">
        Select a run above to see its step-by-step waterfall.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {run.steps.map((step) => {
        const summaryEntries = Object.entries(step.output_summary).filter(
          ([key]) => key !== "updated_keys"
        );
        return (
          <div key={step.id} className="rounded-md border border-border p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">#{step.seq}</span>
                <span className="font-medium">{step.node_name}</span>
                <StatusPill
                  status={step.status}
                  tone={step.status === "done" ? "success" : "destructive"}
                />
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                {step.latency_ms !== null ? <span>{step.latency_ms}ms</span> : null}
                {step.tokens_in > 0 || step.tokens_out > 0 ? (
                  <Badge variant="muted">
                    {step.tokens_in} in / {step.tokens_out} out
                  </Badge>
                ) : null}
              </div>
            </div>
            {step.error ? (
              <p className="mt-2 text-sm text-destructive">{step.error}</p>
            ) : summaryEntries.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                {summaryEntries.map(([key, value]) => (
                  <span key={key}>
                    {key.replace(/_/g, " ")}: {formatSummaryValue(value)}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
