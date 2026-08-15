import type { EvalRunMode, EvalRunOut } from "@/lib/types";

const MODE_LABELS: Record<EvalRunMode, string> = {
  vector: "Vector only",
  vector_bm25: "Vector + BM25",
  full: "Vector + BM25 + Graph (full)",
};

const MODE_ORDER: EvalRunMode[] = ["vector", "vector_bm25", "full"];

function formatPercent(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

function latestRunPerMode(runs: EvalRunOut[]): Map<EvalRunMode, EvalRunOut> {
  const latest = new Map<EvalRunMode, EvalRunOut>();
  for (const run of runs) {
    if (run.mode === null) continue;
    const existing = latest.get(run.mode);
    if (!existing || run.started_at > existing.started_at) {
      latest.set(run.mode, run);
    }
  }
  return latest;
}

export function AblationTable({
  runs,
  onSelectRun,
}: {
  runs: EvalRunOut[];
  onSelectRun: (runId: string) => void;
}): React.JSX.Element {
  const latest = latestRunPerMode(runs);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted-foreground">
            <th className="pb-2 pr-4 font-medium">Configuration</th>
            <th className="pb-2 pr-4 font-medium">recall@1</th>
            <th className="pb-2 pr-4 font-medium">recall@5</th>
            <th className="pb-2 font-medium">MRR</th>
          </tr>
        </thead>
        <tbody>
          {MODE_ORDER.map((mode) => {
            const run = latest.get(mode);
            return (
              <tr key={mode} className="border-b border-border last:border-0">
                <td className="py-2 pr-4">
                  {run ? (
                    <button
                      type="button"
                      onClick={() => onSelectRun(run.id)}
                      className="text-left hover:underline"
                    >
                      {MODE_LABELS[mode]}
                    </button>
                  ) : (
                    MODE_LABELS[mode]
                  )}
                </td>
                <td className="py-2 pr-4 tabular-nums">
                  {run ? formatPercent(run.recall_at_1) : "not yet run"}
                </td>
                <td className="py-2 pr-4 tabular-nums">
                  {run ? formatPercent(run.recall_at_5) : "not yet run"}
                </td>
                <td className="py-2 tabular-nums">
                  {run ? formatPercent(run.mrr) : "not yet run"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
