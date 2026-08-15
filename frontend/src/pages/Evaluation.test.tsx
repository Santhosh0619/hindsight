import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Evaluation } from "@/pages/Evaluation";
import type { EvalRunDetailOut, EvalRunOut } from "@/lib/types";

const mockUseAuth = vi.fn();
vi.mock("@/lib/auth", () => ({
  useAuth: () => mockUseAuth(),
}));

const mockListEvalRuns = vi.fn();
const mockGetEvalRun = vi.fn();
vi.mock("@/lib/api", () => ({
  listEvalRuns: (...args: unknown[]) => mockListEvalRuns(...args),
  getEvalRun: (...args: unknown[]) => mockGetEvalRun(...args),
}));

mockUseAuth.mockReturnValue({
  currentMembership: {
    workspace_id: "w1",
    workspace_name: "W",
    workspace_slug: "w",
    role: "owner",
  },
});

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

const RUN_DETAIL: EvalRunDetailOut = {
  ...RUN,
  results: [
    {
      id: "result-1",
      eval_case_id: "case-1",
      case_name: "connection_pool_exhaustion-primary",
      retrieved_ids: [],
      rank_of_first_hit: null,
      groundedness: null,
      passed: false,
    },
  ],
};

function renderPage(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Evaluation />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Evaluation", () => {
  beforeEach(() => {
    // These two mocks aren't auto-reset between tests -- without this, an earlier
    // test's resolved value and call history would leak into the next test's
    // assertions (e.g. "was getEvalRun called" would see a stale prior call).
    mockListEvalRuns.mockReset();
    mockGetEvalRun.mockReset();
  });

  it("renders metric cards, the ablation table, and the failing case first", async () => {
    mockListEvalRuns.mockResolvedValue([RUN]);
    mockGetEvalRun.mockResolvedValue(RUN_DETAIL);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("connection_pool_exhaustion-primary")).toBeInTheDocument();
    });
    expect(screen.getByText("Vector + BM25 + Graph (full)")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("shows an empty state when there are no eval runs yet", async () => {
    mockListEvalRuns.mockResolvedValue([]);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("No evaluation runs yet")).toBeInTheDocument();
    });
    expect(mockGetEvalRun).not.toHaveBeenCalled();
  });

  it("shows an error state when the runs list fails to load", async () => {
    mockListEvalRuns.mockRejectedValue(new Error("boom"));
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Couldn't load evaluation runs")).toBeInTheDocument();
    });
  });
});
