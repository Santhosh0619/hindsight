import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { FragileServicesTable } from "@/components/dashboard/FragileServicesTable";
import type { FragileServiceOut } from "@/lib/types";

const SERVICE: FragileServiceOut = {
  service: {
    id: "svc-1",
    name: "checkout-api",
    tier: 1,
    team_id: null,
    repo_url: null,
    description: null,
    runbook_url: null,
  },
  incident_count: 3,
  blast_radius_size: 2,
  fragility_score: 9,
};

describe("FragileServicesTable", () => {
  it("renders each service's incident count, blast radius, and fragility score", () => {
    render(
      <MemoryRouter>
        <FragileServicesTable services={[SERVICE]} />
      </MemoryRouter>
    );

    expect(screen.getByText("checkout-api")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("9")).toBeInTheDocument();
  });

  it("shows an empty-state message with no services", () => {
    render(
      <MemoryRouter>
        <FragileServicesTable services={[]} />
      </MemoryRouter>
    );

    expect(screen.getByText("No services to rank yet.")).toBeInTheDocument();
  });
});
