import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AgentRuns } from "@/pages/AgentRuns";
import type { AgentRunDetailOut, AgentRunOut, AgentRunStatsOut } from "@/lib/types";

const mockUseAuth = vi.fn();
vi.mock("@/lib/auth", () => ({
  useAuth: () => mockUseAuth(),
}));

const mockListAgentRuns = vi.fn();
const mockGetAgentRunStats = vi.fn();
const mockGetAgentRun = vi.fn();
vi.mock("@/lib/api", () => ({
  listAgentRuns: (...args: unknown[]) => mockListAgentRuns(...args),
  getAgentRunStats: (...args: unknown[]) => mockGetAgentRunStats(...args),
  getAgentRun: (...args: unknown[]) => mockGetAgentRun(...args),
}));

mockUseAuth.mockReturnValue({
  currentMembership: {
    workspace_id: "w1",
    workspace_name: "W",
    workspace_slug: "w",
    role: "owner",
  },
});

const RUN: AgentRunOut = {
  id: "run-1",
  incident_id: "inc-1",
  incident_title: "checkout-api 500s",
  status: "done",
  started_at: "2026-08-15T00:00:00Z",
  finished_at: "2026-08-15T00:00:10Z",
  total_tokens_in: 500,
  total_tokens_out: 200,
  from_cache: false,
};

const STATS: AgentRunStatsOut = {
  total_runs: 1,
  total_tokens_in: 500,
  total_tokens_out: 200,
  cache_hit_rate: 0,
};

const RUN_DETAIL: AgentRunDetailOut = { ...RUN, steps: [] };

function renderPage(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AgentRuns />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AgentRuns", () => {
  beforeEach(() => {
    mockListAgentRuns.mockReset();
    mockGetAgentRunStats.mockReset();
    mockGetAgentRun.mockReset();
  });

  it("renders stats and the runs table", async () => {
    mockListAgentRuns.mockResolvedValue({ items: [RUN], next_cursor: null });
    mockGetAgentRunStats.mockResolvedValue(STATS);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("checkout-api 500s")).toBeInTheDocument();
    });
    expect(mockGetAgentRun).not.toHaveBeenCalled();
  });

  it("loads a run's waterfall once its row is clicked", async () => {
    mockListAgentRuns.mockResolvedValue({ items: [RUN], next_cursor: null });
    mockGetAgentRunStats.mockResolvedValue(STATS);
    mockGetAgentRun.mockResolvedValue(RUN_DETAIL);
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => screen.getByText("checkout-api 500s"));
    await user.click(screen.getByText("checkout-api 500s"));

    await waitFor(() => {
      expect(mockGetAgentRun).toHaveBeenCalledWith("w1", "run-1");
    });
  });

  it("shows an empty state when there are no runs yet", async () => {
    mockListAgentRuns.mockResolvedValue({ items: [], next_cursor: null });
    mockGetAgentRunStats.mockResolvedValue({ ...STATS, total_runs: 0, cache_hit_rate: null });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("No agent runs yet")).toBeInTheDocument();
    });
  });

  it("shows an error state when the runs list fails to load", async () => {
    mockListAgentRuns.mockRejectedValue(new Error("boom"));
    mockGetAgentRunStats.mockResolvedValue(STATS);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Couldn't load agent runs")).toBeInTheDocument();
    });
  });
});
