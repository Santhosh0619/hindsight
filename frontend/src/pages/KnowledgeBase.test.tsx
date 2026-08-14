import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { KnowledgeBase } from "@/pages/KnowledgeBase";
import type { CursorPage, PostmortemOut } from "@/lib/types";

const mockUseAuth = vi.fn();
const mockUseRequireRole = vi.fn();
vi.mock("@/lib/auth", () => ({
  useAuth: () => mockUseAuth(),
  useRequireRole: (...roles: string[]) => mockUseRequireRole(...roles),
}));

const mockListPostmortems = vi.fn();
vi.mock("@/lib/api", () => ({
  listPostmortems: (...args: unknown[]) => mockListPostmortems(...args),
}));

mockUseAuth.mockReturnValue({
  currentMembership: {
    workspace_id: "w1",
    workspace_name: "W",
    workspace_slug: "w",
    role: "owner",
  },
});

const POSTMORTEM: PostmortemOut = {
  id: "pm-1",
  external_ref: null,
  title: "Checkout outage",
  occurred_at: "2026-01-01T00:00:00Z",
  duration_minutes: 20,
  severity: "sev1",
  status: "indexed",
  injection_flagged: false,
  failure_reason: null,
  created_at: "2026-01-01T00:00:00Z",
  affected_services: [
    {
      service: {
        id: "svc-1",
        name: "checkout-api",
        tier: 1,
        team_id: null,
        repo_url: null,
        description: null,
        runbook_url: null,
      },
      role: "root_cause",
      confidence: 0.9,
    },
  ],
};

function renderPage(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <KnowledgeBase />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("KnowledgeBase", () => {
  it("renders each postmortem with its status and affected services", async () => {
    mockUseRequireRole.mockReturnValue(true);
    mockListPostmortems.mockResolvedValue({
      items: [POSTMORTEM],
      next_cursor: null,
    } satisfies CursorPage<PostmortemOut>);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Checkout outage")).toBeInTheDocument();
    });
    expect(screen.getByText("checkout-api")).toBeInTheDocument();
    // "indexed" also appears as a <select> option; the status pill is the second match.
    expect(screen.getAllByText("indexed")).toHaveLength(2);
  });

  it("shows the empty state when there are no postmortems", async () => {
    mockUseRequireRole.mockReturnValue(true);
    mockListPostmortems.mockResolvedValue({ items: [], next_cursor: null });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("No postmortems yet")).toBeInTheDocument();
    });
  });

  it("hides the New postmortem button for a viewer", async () => {
    mockUseRequireRole.mockReturnValue(false);
    mockListPostmortems.mockResolvedValue({ items: [], next_cursor: null });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("No postmortems yet")).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: "New postmortem" })).not.toBeInTheDocument();
  });

  it("shows the New postmortem button for an owner", async () => {
    mockUseRequireRole.mockReturnValue(true);
    mockListPostmortems.mockResolvedValue({ items: [], next_cursor: null });
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "New postmortem" })).toBeInTheDocument();
    });
  });
});
