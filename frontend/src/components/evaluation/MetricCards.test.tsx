import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MetricCards } from "@/components/evaluation/MetricCards";
import type { EvalRunOut } from "@/lib/types";

const RUN: EvalRunOut = {
  id: "run-1",
  mode: "full",
  started_at: "2026-08-15T00:00:00Z",
  finished_at: "2026-08-15T00:00:10Z",
  recall_at_1: 0.7,
  recall_at_5: 0.95,
  mrr: 0.8,
  groundedness: null,
  citation_validity: 1.0,
  cases_run: 20,
};

describe("MetricCards", () => {
  it("renders formatted percentages for every metric", () => {
    render(<MetricCards run={RUN} />);

    expect(screen.getByText("70%")).toBeInTheDocument();
    expect(screen.getByText("95%")).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  it("shows a dash (never 0%) and an explanatory note when groundedness is null", () => {
    render(<MetricCards run={RUN} />);

    expect(screen.getByText("no LLM key configured")).toBeInTheDocument();
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThan(0);
  });

  it("shows dashes for every metric when there is no run at all", () => {
    render(<MetricCards run={null} />);

    const dashes = screen.getAllByText("—");
    expect(dashes).toHaveLength(5);
  });

  it("shows a dash and an explanatory note when citation_validity is null", () => {
    render(<MetricCards run={{ ...RUN, citation_validity: null }} />);

    expect(screen.getByText("no citations to check")).toBeInTheDocument();
  });
});
