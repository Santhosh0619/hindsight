import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AblationTable } from "@/components/evaluation/AblationTable";
import type { EvalRunOut } from "@/lib/types";

function run(overrides: Partial<EvalRunOut>): EvalRunOut {
  return {
    id: "run-id",
    mode: "full",
    started_at: "2026-08-15T00:00:00Z",
    finished_at: "2026-08-15T00:00:10Z",
    recall_at_1: 0.5,
    recall_at_5: 0.9,
    mrr: 0.7,
    groundedness: null,
    citation_validity: 1.0,
    cases_run: 20,
    ...overrides,
  };
}

describe("AblationTable", () => {
  it("groups runs by mode and shows only the most recent run per mode", () => {
    const runs: EvalRunOut[] = [
      run({
        id: "vector-old",
        mode: "vector",
        started_at: "2026-08-14T00:00:00Z",
        recall_at_5: 0.3,
      }),
      run({
        id: "vector-new",
        mode: "vector",
        started_at: "2026-08-15T00:00:00Z",
        recall_at_5: 0.6,
      }),
      run({
        id: "full-1",
        mode: "full",
        started_at: "2026-08-15T00:00:00Z",
        recall_at_5: 0.95,
      }),
    ];
    render(<AblationTable runs={runs} onSelectRun={vi.fn()} />);

    expect(screen.getByText("60%")).toBeInTheDocument();
    expect(screen.queryByText("30%")).not.toBeInTheDocument();
    expect(screen.getByText("95%")).toBeInTheDocument();
  });

  it("shows 'not yet run' in every cell (not just the first column) for a mode without a run", () => {
    const runs: EvalRunOut[] = [run({ id: "full-1", mode: "full" })];
    render(<AblationTable runs={runs} onSelectRun={vi.fn()} />);

    // vector and vector_bm25 both have no runs yet -- 3 columns (recall@1, recall@5,
    // MRR) each, so 6 total, not just 2. A fix that only handles the first column
    // would pass a getAllByText(...).toHaveLength(2) assertion despite leaving the
    // other two columns blank -- this count is what actually catches that.
    expect(screen.getAllByText("not yet run")).toHaveLength(6);
  });

  it("calls onSelectRun with the run id when a mode row is clicked", () => {
    const onSelectRun = vi.fn();
    const runs: EvalRunOut[] = [run({ id: "full-1", mode: "full" })];
    render(<AblationTable runs={runs} onSelectRun={onSelectRun} />);

    fireEvent.click(screen.getByText("Vector + BM25 + Graph (full)"));
    expect(onSelectRun).toHaveBeenCalledWith("full-1");
  });
});
