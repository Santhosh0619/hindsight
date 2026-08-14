import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ServiceMap } from "@/pages/ServiceMap";
import type { CatalogGraphOut, TeamOut } from "@/lib/types";

const mockUseAuth = vi.fn();
vi.mock("@/lib/auth", () => ({
  useAuth: () => mockUseAuth(),
}));

const mockGetGraph = vi.fn();
const mockListTeams = vi.fn();
const mockGetBlastRadius = vi.fn();
const mockListIncidents = vi.fn();
vi.mock("@/lib/api", () => ({
  getGraph: (...args: unknown[]) => mockGetGraph(...args),
  listTeams: (...args: unknown[]) => mockListTeams(...args),
  getBlastRadius: (...args: unknown[]) => mockGetBlastRadius(...args),
  listIncidents: (...args: unknown[]) => mockListIncidents(...args),
}));

mockUseAuth.mockReturnValue({
  currentMembership: {
    workspace_id: "w1",
    workspace_name: "W",
    workspace_slug: "w",
    role: "owner",
  },
});

const GRAPH: CatalogGraphOut = {
  nodes: [
    {
      id: "svc-1",
      name: "checkout-api",
      tier: 1,
      team_id: null,
      repo_url: null,
      description: null,
      runbook_url: null,
    },
  ],
  edges: [],
};

const TEAMS: TeamOut[] = [];

function renderPage(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ServiceMap />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ServiceMap", () => {
  it("renders the graph once it loads", async () => {
    mockGetGraph.mockResolvedValue(GRAPH);
    mockListTeams.mockResolvedValue(TEAMS);
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "checkout-api" })).toBeInTheDocument();
    });
  });

  it("shows the empty state when the catalog has no services", async () => {
    mockGetGraph.mockResolvedValue({ nodes: [], edges: [] });
    mockListTeams.mockResolvedValue(TEAMS);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("No services yet")).toBeInTheDocument();
    });
  });

  it("shows a distinct error state when the graph fails to load", async () => {
    mockGetGraph.mockRejectedValue(new Error("boom"));
    mockListTeams.mockResolvedValue(TEAMS);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Couldn't load the service map")).toBeInTheDocument();
    });
    expect(screen.queryByText("No services yet")).not.toBeInTheDocument();
  });

  it("opens the side panel with a real blast-radius highlight on node click", async () => {
    mockGetGraph.mockResolvedValue(GRAPH);
    mockListTeams.mockResolvedValue(TEAMS);
    mockGetBlastRadius.mockResolvedValue({ services: [] });
    mockListIncidents.mockResolvedValue({ items: [], next_cursor: null });
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "checkout-api" })).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "checkout-api" }));

    await waitFor(() => {
      expect(mockGetBlastRadius).toHaveBeenCalledWith("w1", "svc-1");
    });
    expect(screen.getByRole("heading", { name: "checkout-api" })).toBeInTheDocument();
  });
});
