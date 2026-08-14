import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/layout/AppShell";

const mockUseAuth = vi.fn();
const mockUseRequireRole = vi.fn();

vi.mock("@/lib/auth", () => ({
  useAuth: () => mockUseAuth(),
  useRequireRole: (...roles: string[]) => mockUseRequireRole(...roles),
}));

function renderShell(): void {
  render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/dashboard" element={<div>Dashboard content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

describe("AppShell — FR-07 role gating", () => {
  it("hides the Settings nav entry for a viewer-role membership", () => {
    mockUseAuth.mockReturnValue({
      user: { id: "1", email: "v@example.com", full_name: "Viewer User", is_demo: false },
      memberships: [
        { workspace_id: "w1", workspace_name: "W", workspace_slug: "w", role: "viewer" },
      ],
      currentMembership: {
        workspace_id: "w1",
        workspace_name: "W",
        workspace_slug: "w",
        role: "viewer",
      },
      setCurrentWorkspace: vi.fn(),
      logout: vi.fn(),
    });
    mockUseRequireRole.mockReturnValue(false);

    renderShell();

    expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "New Incident" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("shows the Settings nav entry for an owner-role membership", () => {
    mockUseAuth.mockReturnValue({
      user: { id: "2", email: "o@example.com", full_name: "Owner User", is_demo: false },
      memberships: [
        { workspace_id: "w1", workspace_name: "W", workspace_slug: "w", role: "owner" },
      ],
      currentMembership: {
        workspace_id: "w1",
        workspace_name: "W",
        workspace_slug: "w",
        role: "owner",
      },
      setCurrentWorkspace: vi.fn(),
      logout: vi.fn(),
    });
    mockUseRequireRole.mockReturnValue(true);

    renderShell();

    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New Incident" })).toBeInTheDocument();
  });
});
