import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RunWaterfall } from "@/components/agent-runs/RunWaterfall";
import type { AgentRunDetailOut } from "@/lib/types";

const RUN: AgentRunDetailOut = {
  id: "run-1",
  incident_id: "inc-1",
  incident_title: "checkout-api 500s",
  status: "done",
  started_at: "2026-08-15T00:00:00Z",
  finished_at: "2026-08-15T00:00:10Z",
  total_tokens_in: 500,
  total_tokens_out: 200,
  from_cache: false,
  steps: [
    {
      id: "step-1",
      seq: 1,
      node_name: "normalizer",
      status: "done",
      latency_ms: 320,
      tokens_in: 500,
      tokens_out: 200,
      output_summary: { updated_keys: ["signal"], affected_service_count: 2 },
      error: null,
    },
    {
      id: "step-2",
      seq: 2,
      node_name: "retriever",
      status: "error",
      latency_ms: null,
      tokens_in: 0,
      tokens_out: 0,
      output_summary: { updated_keys: [] },
      error: "vector store unavailable",
    },
  ],
};

describe("RunWaterfall", () => {
  it("prompts to select a run when none is given", () => {
    render(<RunWaterfall run={null} />);

    expect(
      screen.getByText("Select a run above to see its step-by-step waterfall.")
    ).toBeInTheDocument();
  });

  it("renders one row per step, in seq order, with a summary line", () => {
    render(<RunWaterfall run={RUN} />);

    expect(screen.getByText("normalizer")).toBeInTheDocument();
    expect(screen.getByText("retriever")).toBeInTheDocument();
    expect(screen.getByText(/affected service count: 2/)).toBeInTheDocument();
    expect(screen.getByText("320ms")).toBeInTheDocument();
  });

  it("shows the step error instead of a summary when the step failed", () => {
    render(<RunWaterfall run={RUN} />);

    expect(screen.getByText("vector store unavailable")).toBeInTheDocument();
  });
});
