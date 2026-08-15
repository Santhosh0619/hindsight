import { MetricCard } from "@/components/ui/metric-card";
import type { AgentRunStatsOut } from "@/lib/types";

function formatPercent(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export function RunStatsCards({ stats }: { stats: AgentRunStatsOut | null }): React.JSX.Element {
  return (
    <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <MetricCard label="Total runs" value={stats?.total_runs ?? "—"} />
      <MetricCard label="Tokens in" value={stats?.total_tokens_in ?? "—"} />
      <MetricCard label="Tokens out" value={stats?.total_tokens_out ?? "—"} />
      <MetricCard
        label="Cache hit rate"
        value={formatPercent(stats?.cache_hit_rate ?? null)}
        description={stats && stats.total_runs === 0 ? "no runs yet" : undefined}
      />
    </div>
  );
}
