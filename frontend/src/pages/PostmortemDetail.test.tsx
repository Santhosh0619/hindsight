import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { PostmortemDetail } from "@/pages/PostmortemDetail";
import type { PostmortemDetailOut } from "@/lib/types";

const mockUseAuth = vi.fn();
vi.mock("@/lib/auth", () => ({
  useAuth: () => mockUseAuth(),
}));

const mockGetPostmortem = vi.fn();
vi.mock("@/lib/api", () => ({
  getPostmortem: (...args: unknown[]) => mockGetPostmortem(...args),
}));

mockUseAuth.mockReturnValue({
  currentMembership: {
    workspace_id: "w1",
    workspace_name: "W",
    workspace_slug: "w",
    role: "owner",
  },
});

const DETAIL: PostmortemDetailOut = {
  id: "pm-1",
  external_ref: null,
  title: "Checkout outage",
  occurred_at: null,
  duration_minutes: null,
  severity: "sev1",
  status: "indexed",
  injection_flagged: false,
  failure_reason: null,
  created_at: "2026-01-01T00:00:00Z",
  affected_services: [],
  chunks: [],
  redacted_text: "The pool was exhausted after a bad deploy.",
  facts: [
    {
      fact_type: "root_cause",
      statement: "A bad deploy exhausted the pool",
      confidence: 0.8,
      source_chunk_id: "chunk-1",
      char_start: 4,
      char_end: 22,
    },
  ],
};

function renderPage(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/knowledge-base/pm-1"]}>
        <Routes>
          <Route path="/knowledge-base/:id" element={<PostmortemDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("PostmortemDetail", () => {
  it("renders the extracted fact list alongside the highlighted document", async () => {
    mockGetPostmortem.mockResolvedValue(DETAIL);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("A bad deploy exhausted the pool")).toBeInTheDocument();
    });
    expect(screen.getByText("Root cause")).toBeInTheDocument();
    // The highlighted span itself renders inline as part of the document text.
    expect(screen.getByText(/pool was exhausted/)).toBeInTheDocument();
  });

  it("shows the injection warning banner when the postmortem is flagged", async () => {
    mockGetPostmortem.mockResolvedValue({ ...DETAIL, injection_flagged: true });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/suspected prompt-injection attempt/)).toBeInTheDocument();
    });
  });

  it("does not show the injection banner when the postmortem is clean", async () => {
    mockGetPostmortem.mockResolvedValue(DETAIL);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Checkout outage")).toBeInTheDocument();
    });
    expect(screen.queryByText(/suspected prompt-injection attempt/)).not.toBeInTheDocument();
  });

  it("shows an empty-facts message when nothing has been extracted", async () => {
    mockGetPostmortem.mockResolvedValue({ ...DETAIL, facts: [] });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("No facts extracted yet.")).toBeInTheDocument();
    });
  });

  it("shows a processing message when the document isn't available yet", async () => {
    mockGetPostmortem.mockResolvedValue({
      ...DETAIL,
      status: "processing",
      redacted_text: null,
      facts: [],
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Still processing/)).toBeInTheDocument();
    });
  });
});
