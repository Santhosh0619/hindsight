import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EvalTrendChart } from "@/components/evaluation/EvalTrendChart";
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

describe("EvalTrendChart", () => {
  it("shows the empty-data message with no runs", () => {
    render(<EvalTrendChart runs={[]} onSelectRun={vi.fn()} />);

    expect(
      screen.getByText("No evaluation runs yet -- run `make eval` to produce one.")
    ).toBeInTheDocument();
  });

  it("renders a chart when at least one run exists", () => {
    const { container } = render(<EvalTrendChart runs={[run({})]} onSelectRun={vi.fn()} />);

    expect(container.querySelector(".recharts-responsive-container")).toBeInTheDocument();
  });
});
