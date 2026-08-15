import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RunsTable } from "@/components/agent-runs/RunsTable";
import type { AgentRunOut } from "@/lib/types";

const RUNS: AgentRunOut[] = [
  {
    id: "run-1",
    incident_id: "inc-1",
    incident_title: "checkout-api 500s",
    status: "done",
    started_at: "2026-08-15T00:00:00Z",
    finished_at: "2026-08-15T00:00:10Z",
    total_tokens_in: 500,
    total_tokens_out: 200,
    from_cache: true,
  },
  {
    id: "run-2",
    incident_id: "inc-2",
    incident_title: "payments-svc timeouts",
    status: "error",
    started_at: "2026-08-15T00:05:00Z",
    finished_at: null,
    total_tokens_in: 0,
    total_tokens_out: 0,
    from_cache: false,
  },
];

describe("RunsTable", () => {
  it("renders one row per run with status and cache badge", () => {
    render(<RunsTable runs={RUNS} selectedRunId={null} onSelectRun={vi.fn()} />);

    expect(screen.getByText("checkout-api 500s")).toBeInTheDocument();
    expect(screen.getByText("payments-svc timeouts")).toBeInTheDocument();
    expect(screen.getByText("cached")).toBeInTheDocument();
    expect(screen.getByText("done")).toBeInTheDocument();
    expect(screen.getByText("error")).toBeInTheDocument();
  });

  it("calls onSelectRun with the run id when a row is clicked", async () => {
    const onSelectRun = vi.fn();
    const user = userEvent.setup();
    render(<RunsTable runs={RUNS} selectedRunId={null} onSelectRun={onSelectRun} />);

    await user.click(screen.getByText("checkout-api 500s"));

    expect(onSelectRun).toHaveBeenCalledWith("run-1");
  });

  it("shows an empty state when there are no runs", () => {
    render(<RunsTable runs={[]} selectedRunId={null} onSelectRun={vi.fn()} />);

    expect(screen.getByText("No agent runs yet.")).toBeInTheDocument();
  });
});
