import { MetricCard } from "@/components/ui/metric-card";
import type { EvalRunOut } from "@/lib/types";

function formatPercent(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export function MetricCards({ run }: { run: EvalRunOut | null }): React.JSX.Element {
  return (
    <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
      <MetricCard label="Recall@1" value={formatPercent(run?.recall_at_1 ?? null)} />
      <MetricCard label="Recall@5" value={formatPercent(run?.recall_at_5 ?? null)} />
      <MetricCard label="MRR" value={formatPercent(run?.mrr ?? null)} />
      <MetricCard label="Citation validity" value={formatPercent(run?.citation_validity ?? null)} />
      <MetricCard
        label="Groundedness"
        value={formatPercent(run?.groundedness ?? null)}
        description={run && run.groundedness === null ? "no LLM key configured" : undefined}
      />
    </div>
  );
}
