import { Badge } from "@/components/ui/badge";
import type { EvalCaseResultOut } from "@/lib/types";

function formatPercent(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export function CaseResultsTable({ results }: { results: EvalCaseResultOut[] }): React.JSX.Element {
  if (results.length === 0) {
    return <p className="text-sm text-muted-foreground">No case results for this run.</p>;
  }

  // Failing cases are the most interesting part of this page -- surface them first,
  // not buried under an aggregate score.
  const ordered = [...results].sort((a, b) => Number(a.passed) - Number(b.passed));

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted-foreground">
            <th className="pb-2 pr-4 font-medium">Case</th>
            <th className="pb-2 pr-4 font-medium">Rank of first hit</th>
            <th className="pb-2 pr-4 font-medium">Groundedness</th>
            <th className="pb-2 font-medium">Result</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((result) => (
            <tr key={result.id} className="border-b border-border last:border-0">
              <td className="py-2 pr-4">{result.case_name}</td>
              <td className="py-2 pr-4 tabular-nums">
                {result.rank_of_first_hit === null ? "not retrieved" : result.rank_of_first_hit}
              </td>
              <td className="py-2 pr-4 tabular-nums">{formatPercent(result.groundedness)}</td>
              <td className="py-2">
                <Badge variant={result.passed ? "success" : "destructive"}>
                  {result.passed ? "passed" : "failed"}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
