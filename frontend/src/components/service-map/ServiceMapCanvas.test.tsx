import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ServiceMapCanvas } from "@/components/service-map/ServiceMapCanvas";
import type { EdgeOut, ServiceOut, TeamOut } from "@/lib/types";

const SERVICES: ServiceOut[] = [
  {
    id: "svc-1",
    name: "checkout-api",
    tier: 1,
    team_id: "team-1",
    repo_url: null,
    description: null,
    runbook_url: null,
  },
  {
    id: "svc-2",
    name: "payments-svc",
    tier: 2,
    team_id: null,
    repo_url: null,
    description: null,
    runbook_url: null,
  },
];

const EDGES: EdgeOut[] = [
  {
    id: "edge-1",
    from_service_id: "svc-1",
    to_service_id: "svc-2",
    kind: "calls",
    criticality: "hard",
  },
];

const TEAMS: TeamOut[] = [
  { id: "team-1", name: "Checkout", slack_handle: null, escalation_contact: null },
];

describe("ServiceMapCanvas", () => {
  it("renders every service as a labeled node", () => {
    render(
      <ServiceMapCanvas
        nodes={SERVICES}
        edges={EDGES}
        teams={TEAMS}
        selectedServiceId={null}
        highlightedServiceIds={new Set()}
        onSelectService={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: "checkout-api" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "payments-svc" })).toBeInTheDocument();
  });

  it("calls onSelectService when a node is clicked", async () => {
    const onSelectService = vi.fn();
    const user = userEvent.setup();
    render(
      <ServiceMapCanvas
        nodes={SERVICES}
        edges={EDGES}
        teams={TEAMS}
        selectedServiceId={null}
        highlightedServiceIds={new Set()}
        onSelectService={onSelectService}
      />
    );

    await user.click(screen.getByRole("button", { name: "checkout-api" }));

    expect(onSelectService).toHaveBeenCalledWith("svc-1");
  });

  it("calls onSelectService when a node is activated via keyboard", async () => {
    const onSelectService = vi.fn();
    const user = userEvent.setup();
    render(
      <ServiceMapCanvas
        nodes={SERVICES}
        edges={EDGES}
        teams={TEAMS}
        selectedServiceId={null}
        highlightedServiceIds={new Set()}
        onSelectService={onSelectService}
      />
    );

    const node = screen.getByRole("button", { name: "checkout-api" });
    node.focus();
    await user.keyboard("{Enter}");

    expect(onSelectService).toHaveBeenCalledWith("svc-1");
  });

  it("renders an edge referencing a missing node without crashing", () => {
    const edgesWithGhost: EdgeOut[] = [
      {
        id: "e2",
        from_service_id: "svc-1",
        to_service_id: "ghost",
        kind: "calls",
        criticality: "soft",
      },
    ];
    render(
      <ServiceMapCanvas
        nodes={SERVICES}
        edges={edgesWithGhost}
        teams={TEAMS}
        selectedServiceId={null}
        highlightedServiceIds={new Set()}
        onSelectService={vi.fn()}
      />
    );

    expect(screen.getByRole("img", { name: "Service dependency map" })).toBeInTheDocument();
  });
});
