import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Search } from "@/pages/Search";
import type { SearchResponseOut } from "@/lib/types";

const mockUseAuth = vi.fn();
vi.mock("@/lib/auth", () => ({
  useAuth: () => mockUseAuth(),
}));

const mockSearch = vi.fn();
vi.mock("@/lib/api", () => ({
  search: (...args: unknown[]) => mockSearch(...args),
}));

mockUseAuth.mockReturnValue({
  currentMembership: {
    workspace_id: "w1",
    workspace_name: "W",
    workspace_slug: "w",
    role: "owner",
  },
});

function renderSearch(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <Search />
    </QueryClientProvider>
  );
}

const SAMPLE_RESPONSE: SearchResponseOut = {
  mode: "hybrid",
  timings_ms: { vector: 10, keyword: 5, graph: 3, fusion: 1 },
  results: [
    {
      postmortem: {
        id: "pm1",
        external_ref: null,
        title: "Checkout outage",
        occurred_at: null,
        duration_minutes: null,
        severity: "sev2",
        status: "indexed",
        injection_flagged: false,
        failure_reason: null,
        created_at: "2026-01-01T00:00:00Z",
        affected_services: [],
      },
      score: 0.5,
      sources: [
        { source: "vector", rank: 1, raw_score: 0.2 },
        { source: "keyword", rank: 2, raw_score: 1.1 },
      ],
      chunk_excerpt: {
        chunk_id: "c1",
        section_label: "Summary",
        content: "The checkout went down.",
      },
      graph_reason: null,
    },
  ],
};

describe("Search", () => {
  it("prompts for a query before searching anything", () => {
    renderSearch();

    expect(screen.getByText("Search your knowledge base")).toBeInTheDocument();
    expect(mockSearch).not.toHaveBeenCalled();
  });

  it("renders results with a chip per contributing retriever after typing a query", async () => {
    const user = userEvent.setup();
    mockSearch.mockResolvedValue(SAMPLE_RESPONSE);
    renderSearch();

    await user.type(screen.getByLabelText("Search query"), "checkout outage");

    await waitFor(() => expect(screen.getByText("Checkout outage")).toBeInTheDocument());
    expect(screen.getByText("vector #1")).toBeInTheDocument();
    expect(screen.getByText("keyword #2")).toBeInTheDocument();
    expect(screen.getByText(/checkout went down/)).toBeInTheDocument();
    expect(mockSearch).toHaveBeenCalledWith(
      "w1",
      expect.objectContaining({ q: "checkout outage", mode: "hybrid" })
    );
  });

  it("re-queries with the newly selected mode when the toggle changes", async () => {
    const user = userEvent.setup();
    mockSearch.mockResolvedValue(SAMPLE_RESPONSE);
    renderSearch();

    await user.type(screen.getByLabelText("Search query"), "checkout outage");
    await waitFor(() => expect(mockSearch).toHaveBeenCalled());

    await user.click(screen.getByRole("tab", { name: "Keyword" }));

    await waitFor(() =>
      expect(mockSearch).toHaveBeenCalledWith(
        "w1",
        expect.objectContaining({ q: "checkout outage", mode: "keyword" })
      )
    );
  });

  it("shows a distinct empty state when a query returns zero results", async () => {
    const user = userEvent.setup();
    mockSearch.mockResolvedValue({ mode: "hybrid", timings_ms: {}, results: [] });
    renderSearch();

    await user.type(screen.getByLabelText("Search query"), "nothing matches");

    await waitFor(() => expect(screen.getByText("No results")).toBeInTheDocument());
  });
});
