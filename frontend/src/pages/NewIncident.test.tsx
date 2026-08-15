import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { NewIncident } from "@/pages/NewIncident";

const mockUseAuth = vi.fn();
const mockUseCanGenerateBrief = vi.fn();
vi.mock("@/lib/auth", () => ({
  useAuth: () => mockUseAuth(),
  useCanGenerateBrief: () => mockUseCanGenerateBrief(),
}));

vi.mock("@/lib/api", () => ({
  createIncident: vi.fn(),
  listBriefs: vi.fn(),
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

function renderPage(): void {
  render(
    <MemoryRouter>
      <NewIncident />
    </MemoryRouter>
  );
}

describe("NewIncident — demo-guest write gate", () => {
  it("shows the read-only empty state for a plain viewer", () => {
    mockUseCanGenerateBrief.mockReturnValue(false);
    renderPage();

    expect(screen.getByText("Read-only access")).toBeInTheDocument();
    expect(screen.queryByLabelText("Alert text")).not.toBeInTheDocument();
  });

  it("shows the alert form for a demo guest", () => {
    mockUseCanGenerateBrief.mockReturnValue(true);
    renderPage();

    expect(screen.queryByText("Read-only access")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Alert text")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Investigate" })).toBeInTheDocument();
  });
});
