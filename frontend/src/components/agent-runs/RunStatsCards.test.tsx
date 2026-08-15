import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RunStatsCards } from "@/components/agent-runs/RunStatsCards";
import type { AgentRunStatsOut } from "@/lib/types";

const STATS: AgentRunStatsOut = {
  total_runs: 12,
  total_tokens_in: 4000,
  total_tokens_out: 1200,
  cache_hit_rate: 0.25,
};

describe("RunStatsCards", () => {
  it("renders every metric", () => {
    render(<RunStatsCards stats={STATS} />);

    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("4000")).toBeInTheDocument();
    expect(screen.getByText("1200")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
  });

  it("shows a dash (never 0%) when cache_hit_rate is null", () => {
    render(<RunStatsCards stats={{ ...STATS, total_runs: 0, cache_hit_rate: null }} />);

    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("no runs yet")).toBeInTheDocument();
  });

  it("shows dashes for every metric when there are no stats at all", () => {
    render(<RunStatsCards stats={null} />);

    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(4);
  });
});
