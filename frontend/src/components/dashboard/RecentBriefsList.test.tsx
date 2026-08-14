import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { RecentBriefsList } from "@/components/dashboard/RecentBriefsList";
import type { RecentBriefOut } from "@/lib/types";

const BRIEF: RecentBriefOut = {
  incident_id: "inc-1",
  incident_title: "Checkout outage",
  brief_id: "brief-1",
  version: 1,
  overall_confidence: 0.82,
  generated_at: "2026-01-01T00:00:00Z",
};

describe("RecentBriefsList", () => {
  it("renders each brief's incident title, confidence, and generated time", () => {
    render(
      <MemoryRouter>
        <RecentBriefsList briefs={[BRIEF]} />
      </MemoryRouter>
    );

    expect(screen.getByText("Checkout outage")).toBeInTheDocument();
    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Checkout outage/ })).toHaveAttribute(
      "href",
      "/incidents/inc-1"
    );
  });

  it("shows an empty-state message with no briefs", () => {
    render(
      <MemoryRouter>
        <RecentBriefsList briefs={[]} />
      </MemoryRouter>
    );

    expect(screen.getByText("No briefs generated yet.")).toBeInTheDocument();
  });

  it("omits the confidence badge when overall_confidence is null", () => {
    render(
      <MemoryRouter>
        <RecentBriefsList briefs={[{ ...BRIEF, overall_confidence: null }]} />
      </MemoryRouter>
    );

    expect(screen.queryByText("82%")).not.toBeInTheDocument();
  });
});
