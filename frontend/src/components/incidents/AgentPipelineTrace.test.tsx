import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AgentPipelineTrace } from "@/components/incidents/AgentPipelineTrace";
import type { AgentStreamEvent } from "@/lib/types";

describe("AgentPipelineTrace", () => {
  it("shows a node's latency once its node_end event arrives", () => {
    const events: AgentStreamEvent[] = [
      { type: "node_start", node: "normalizer" },
      { type: "node_end", node: "normalizer", latency_ms: 42 },
      { type: "node_start", node: "retriever" },
    ];
    render(<AgentPipelineTrace events={events} />);

    expect(screen.getByText("42ms")).toBeInTheDocument();
    expect(screen.getByText("Retriever")).toBeInTheDocument();
  });

  it("shows the retry label and resets every downstream node's latency", () => {
    const events: AgentStreamEvent[] = [
      { type: "node_start", node: "normalizer" },
      { type: "node_end", node: "normalizer", latency_ms: 10 },
      { type: "node_start", node: "retriever" },
      { type: "node_end", node: "retriever", latency_ms: 20 },
      { type: "node_start", node: "correlator" },
      { type: "node_end", node: "correlator", latency_ms: 5 },
      { type: "node_start", node: "analyst" },
      { type: "node_end", node: "analyst", latency_ms: 30 },
      { type: "node_start", node: "critic" },
      { type: "node_end", node: "critic", latency_ms: 15 },
      { type: "retry" },
      { type: "node_start", node: "retriever" },
    ];
    render(<AgentPipelineTrace events={events} />);

    expect(screen.getByText("Refining retrieval…")).toBeInTheDocument();
    // normalizer never resets on a retry -- only retriever and everything downstream.
    expect(screen.getByText("10ms")).toBeInTheDocument();
    expect(screen.queryByText("20ms")).not.toBeInTheDocument();
    expect(screen.queryByText("5ms")).not.toBeInTheDocument();
    expect(screen.queryByText("30ms")).not.toBeInTheDocument();
    expect(screen.queryByText("15ms")).not.toBeInTheDocument();
  });

  it("shows no retry label and no latencies before anything has run", () => {
    render(<AgentPipelineTrace events={[]} />);

    expect(screen.queryByText("Refining retrieval…")).not.toBeInTheDocument();
    expect(screen.queryByText(/ms$/)).not.toBeInTheDocument();
  });
});
