import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/layout/AppShell";

const mockUseAuth = vi.fn();
const mockUseRequireRole = vi.fn();
const mockUseCanGenerateBrief = vi.fn();
const mockUseIsDemoWorkspace = vi.fn();

vi.mock("@/lib/auth", () => ({
  useAuth: () => mockUseAuth(),
  useRequireRole: (...roles: string[]) => mockUseRequireRole(...roles),
  useCanGenerateBrief: () => mockUseCanGenerateBrief(),
  useIsDemoWorkspace: () => mockUseIsDemoWorkspace(),
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
    mockUseCanGenerateBrief.mockReturnValue(false);
    mockUseIsDemoWorkspace.mockReturnValue(false);

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
    mockUseCanGenerateBrief.mockReturnValue(true);
    mockUseIsDemoWorkspace.mockReturnValue(false);

    renderShell();

    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New Incident" })).toBeInTheDocument();
  });

  it("shows the New Incident nav entry and demo banner for a demo guest viewing the demo workspace", () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: "3",
        email: "guest@demo.hindsight.local",
        full_name: "Demo Guest",
        is_demo: true,
      },
      memberships: [
        {
          workspace_id: "w1",
          workspace_name: "Demo Workspace",
          workspace_slug: "demo",
          workspace_is_demo: true,
          role: "viewer",
        },
      ],
      currentMembership: {
        workspace_id: "w1",
        workspace_name: "Demo Workspace",
        workspace_slug: "demo",
        workspace_is_demo: true,
        role: "viewer",
      },
      setCurrentWorkspace: vi.fn(),
      logout: vi.fn(),
    });
    mockUseRequireRole.mockReturnValue(false);
    mockUseCanGenerateBrief.mockReturnValue(true);
    mockUseIsDemoWorkspace.mockReturnValue(true);

    renderShell();

    expect(screen.getByRole("link", { name: "New Incident" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument();
    expect(screen.getByText(/synthetic data, read-only/i)).toBeInTheDocument();
  });

  it("hides the demo banner for a demo guest viewing a real (non-demo) workspace", () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: "3",
        email: "guest@demo.hindsight.local",
        full_name: "Demo Guest",
        is_demo: true,
      },
      memberships: [
        {
          workspace_id: "w2",
          workspace_name: "Real Workspace",
          workspace_slug: "real",
          workspace_is_demo: false,
          role: "viewer",
        },
      ],
      currentMembership: {
        workspace_id: "w2",
        workspace_name: "Real Workspace",
        workspace_slug: "real",
        workspace_is_demo: false,
        role: "viewer",
      },
      setCurrentWorkspace: vi.fn(),
      logout: vi.fn(),
    });
    mockUseRequireRole.mockReturnValue(false);
    mockUseCanGenerateBrief.mockReturnValue(false);
    mockUseIsDemoWorkspace.mockReturnValue(false);

    renderShell();

    expect(screen.queryByText(/synthetic data, read-only/i)).not.toBeInTheDocument();
  });

  it("highlights only New Incident, not Incidents, when viewing /incidents/new", () => {
    mockUseAuth.mockReturnValue({
      user: { id: "4", email: "r@example.com", full_name: "Responder User", is_demo: false },
      memberships: [
        { workspace_id: "w1", workspace_name: "W", workspace_slug: "w", role: "responder" },
      ],
      currentMembership: {
        workspace_id: "w1",
        workspace_name: "W",
        workspace_slug: "w",
        role: "responder",
      },
      setCurrentWorkspace: vi.fn(),
      logout: vi.fn(),
    });
    mockUseRequireRole.mockReturnValue(true);
    mockUseCanGenerateBrief.mockReturnValue(true);
    mockUseIsDemoWorkspace.mockReturnValue(false);

    render(
      <MemoryRouter initialEntries={["/incidents/new"]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/incidents/new" element={<div>New Incident content</div>} />
            <Route path="/incidents" element={<div>Incidents content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByRole("link", { name: "New Incident" })).toHaveAttribute(
      "aria-current",
      "page"
    );
    expect(screen.getByRole("link", { name: "Incidents" })).not.toHaveAttribute("aria-current");
  });
});
