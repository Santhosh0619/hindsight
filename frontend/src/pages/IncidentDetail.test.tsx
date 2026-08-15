import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { IncidentDetail } from "@/pages/IncidentDetail";
import type { IncidentOut } from "@/lib/types";

const mockUseAuth = vi.fn();
const mockUseCanGenerateBrief = vi.fn();
vi.mock("@/lib/auth", () => ({
  useAuth: () => mockUseAuth(),
  useCanGenerateBrief: () => mockUseCanGenerateBrief(),
}));

const mockGetIncident = vi.fn();
const mockListBriefs = vi.fn();
vi.mock("@/lib/api", () => ({
  getIncident: (...args: unknown[]) => mockGetIncident(...args),
  listBriefs: (...args: unknown[]) => mockListBriefs(...args),
  streamBrief: vi.fn(),
}));

mockUseAuth.mockReturnValue({
  currentMembership: {
    workspace_id: "w1",
    workspace_name: "W",
    workspace_slug: "w",
    role: "viewer",
  },
});

const INCIDENT: IncidentOut = {
  id: "inc-1",
  workspace_id: "w1",
  external_ref: null,
  title: "checkout is down",
  raw_alert_text: "checkout-api throwing 500s",
  severity: "sev2",
  status: "open",
  opened_by: null,
  opened_at: "2026-01-01T00:00:00Z",
  resolved_at: null,
  created_at: "2026-01-01T00:00:00Z",
};

function renderPage(): void {
  render(
    <MemoryRouter initialEntries={["/incidents/inc-1"]}>
      <Routes>
        <Route path="/incidents/:id" element={<IncidentDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("IncidentDetail — demo-guest write gate", () => {
  it("hides the Generate brief action and shows a read-only hint for a plain viewer", async () => {
    mockUseCanGenerateBrief.mockReturnValue(false);
    mockGetIncident.mockResolvedValue(INCIDENT);
    mockListBriefs.mockResolvedValue([]);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("checkout is down")).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: "Generate brief" })).not.toBeInTheDocument();
    expect(screen.getByText("Ask an owner or responder to generate one.")).toBeInTheDocument();
  });

  it("shows the Generate brief action for a demo guest", async () => {
    mockUseCanGenerateBrief.mockReturnValue(true);
    mockGetIncident.mockResolvedValue(INCIDENT);
    mockListBriefs.mockResolvedValue([]);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("checkout is down")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Generate brief" })).toBeInTheDocument();
  });
});
