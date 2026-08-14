import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { Dashboard } from "@/pages/Dashboard";
import type { DashboardOut } from "@/lib/types";

const mockUseAuth = vi.fn();
vi.mock("@/lib/auth", () => ({
  useAuth: () => mockUseAuth(),
}));

const mockGetDashboard = vi.fn();
vi.mock("@/lib/api", () => ({
  getDashboard: (...args: unknown[]) => mockGetDashboard(...args),
}));

mockUseAuth.mockReturnValue({
  currentMembership: {
    workspace_id: "w1",
    workspace_name: "W",
    workspace_slug: "w",
    role: "owner",
  },
});

const DASHBOARD: DashboardOut = {
  open_incidents: 3,
  briefs_generated: 12,
  corpus_size: 40,
  ingest_health: { indexed: 38, processing: 1, pending: 0, failed: 1 },
  mttr_trend: [
    { week_start: "2026-01-05", mttr_minutes: null },
    { week_start: "2026-01-12", mttr_minutes: 90 },
  ],
  fragile_services: [
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
      incident_count: 7,
      blast_radius_size: 5,
      fragility_score: 42,
    },
  ],
  recent_briefs: [
    {
      incident_id: "inc-1",
      incident_title: "Checkout outage",
      brief_id: "brief-1",
      version: 1,
      overall_confidence: 0.82,
      generated_at: "2026-01-01T00:00:00Z",
    },
  ],
};

function renderPage(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Dashboard", () => {
  it("renders the metric cards, fragile services, and recent briefs", async () => {
    mockGetDashboard.mockResolvedValue(DASHBOARD);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Open incidents")).toBeInTheDocument();
    });
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("40")).toBeInTheDocument();
    expect(screen.getByText("checkout-api")).toBeInTheDocument();
    expect(screen.getByText("Checkout outage")).toBeInTheDocument();
  });

  it("shows an error state when the dashboard fails to load", async () => {
    mockGetDashboard.mockRejectedValue(new Error("boom"));
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Couldn't load the dashboard")).toBeInTheDocument();
    });
  });

  it("shows a dash for ingest health with an empty corpus", async () => {
    mockGetDashboard.mockResolvedValue({
      ...DASHBOARD,
      corpus_size: 0,
      ingest_health: { indexed: 0, processing: 0, pending: 0, failed: 0 },
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("—")).toBeInTheDocument();
    });
  });
});
