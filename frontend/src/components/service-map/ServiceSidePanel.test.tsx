import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ServiceSidePanel } from "@/components/service-map/ServiceSidePanel";
import type { BlastRadiusOut, IncidentOut, ServiceOut, TeamOut } from "@/lib/types";

const mockListIncidents = vi.fn();
vi.mock("@/lib/api", () => ({
  listIncidents: (...args: unknown[]) => mockListIncidents(...args),
}));

const SERVICE: ServiceOut = {
  id: "svc-1",
  name: "checkout-api",
  tier: 1,
  team_id: "team-1",
  repo_url: null,
  description: "Handles checkout.",
  runbook_url: "https://runbooks.example.com/checkout",
};

const TEAM: TeamOut = {
  id: "team-1",
  name: "Checkout Team",
  slack_handle: "#checkout",
  escalation_contact: "checkout-oncall@example.com",
};

const BLAST_RADIUS: BlastRadiusOut = {
  services: [
    {
      service: { ...SERVICE, id: "svc-2", name: "payments-svc" },
      score: 0.8,
      path: [],
      depth: 1,
    },
  ],
};

const INCIDENT: IncidentOut = {
  id: "inc-1",
  workspace_id: "w1",
  external_ref: null,
  title: "Checkout outage",
  raw_alert_text: "checkout is down",
  severity: "sev1",
  status: "open",
  opened_by: null,
  opened_at: "2026-01-01T00:00:00Z",
  resolved_at: null,
  created_at: "2026-01-01T00:00:00Z",
};

function renderPanel(overrides: Partial<React.ComponentProps<typeof ServiceSidePanel>> = {}): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ServiceSidePanel
          workspaceId="w1"
          service={SERVICE}
          team={TEAM}
          blastRadius={BLAST_RADIUS}
          blastRadiusLoading={false}
          blastRadiusError={false}
          onClose={vi.fn()}
          {...overrides}
        />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ServiceSidePanel", () => {
  it("shows the owning team's contact info and the runbook link", () => {
    mockListIncidents.mockResolvedValue({ items: [], next_cursor: null });
    renderPanel();

    expect(screen.getByText("Checkout Team")).toBeInTheDocument();
    expect(screen.getByText("#checkout")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /runbooks.example.com/ })).toHaveAttribute(
      "href",
      "https://runbooks.example.com/checkout"
    );
  });

  it("shows 'No team assigned' when the service has no team", () => {
    mockListIncidents.mockResolvedValue({ items: [], next_cursor: null });
    renderPanel({ team: null });

    expect(screen.getByText("No team assigned")).toBeInTheDocument();
  });

  it("renders the resolved blast radius entries", () => {
    mockListIncidents.mockResolvedValue({ items: [], next_cursor: null });
    renderPanel();

    expect(screen.getByText("payments-svc")).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument();
  });

  it("renders incident history once it resolves", async () => {
    mockListIncidents.mockResolvedValue({ items: [INCIDENT], next_cursor: null });
    renderPanel();

    await waitFor(() => {
      expect(screen.getByText("Checkout outage")).toBeInTheDocument();
    });
  });

  it("shows an empty state when there is no incident history", async () => {
    mockListIncidents.mockResolvedValue({ items: [], next_cursor: null });
    renderPanel();

    await waitFor(() => {
      expect(screen.getByText("No incidents recorded")).toBeInTheDocument();
    });
  });

  it("shows a distinct error when the blast radius fails to load", () => {
    mockListIncidents.mockResolvedValue({ items: [], next_cursor: null });
    renderPanel({ blastRadius: undefined, blastRadiusError: true });

    expect(screen.getByText("Couldn't load blast radius.")).toBeInTheDocument();
    expect(screen.queryByText("No downstream impact")).not.toBeInTheDocument();
  });

  it("shows a distinct error when incident history fails to load", async () => {
    mockListIncidents.mockRejectedValue(new Error("boom"));
    renderPanel();

    await waitFor(() => {
      expect(screen.getByText("Couldn't load incident history.")).toBeInTheDocument();
    });
    expect(screen.queryByText("No incidents recorded")).not.toBeInTheDocument();
  });
});
