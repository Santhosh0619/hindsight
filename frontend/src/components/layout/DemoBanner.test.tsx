import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DemoBanner } from "@/components/layout/DemoBanner";

const mockUseAuth = vi.fn();

vi.mock("@/lib/auth", () => ({
  useAuth: () => mockUseAuth(),
}));

describe("DemoBanner", () => {
  it("renders the synthetic-data notice for a demo guest viewing the demo workspace", () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: "1",
        email: "guest@demo.hindsight.local",
        full_name: "Demo Guest",
        is_demo: true,
      },
      currentMembership: {
        workspace_id: "w1",
        workspace_name: "Demo Workspace",
        workspace_slug: "demo",
        workspace_is_demo: true,
        role: "viewer",
      },
    });

    render(<DemoBanner />);

    expect(screen.getByText(/demo workspace.*synthetic data.*read-only/i)).toBeInTheDocument();
  });

  it("renders nothing for a demo guest viewing a real (non-demo) workspace they've also joined", () => {
    // Regression guard: a demo guest's is_demo flag is permanent on the account, so
    // this must not render just because the account is a demo guest -- only when
    // the workspace currently being viewed is itself the demo workspace.
    mockUseAuth.mockReturnValue({
      user: {
        id: "1",
        email: "guest@demo.hindsight.local",
        full_name: "Demo Guest",
        is_demo: true,
      },
      currentMembership: {
        workspace_id: "w2",
        workspace_name: "Real Workspace",
        workspace_slug: "real",
        workspace_is_demo: false,
        role: "viewer",
      },
    });

    const { container } = render(<DemoBanner />);

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing for a real (non-demo) user", () => {
    mockUseAuth.mockReturnValue({
      user: { id: "2", email: "owner@example.com", full_name: "Owner User", is_demo: false },
      currentMembership: {
        workspace_id: "w2",
        workspace_name: "Real Workspace",
        workspace_slug: "real",
        workspace_is_demo: false,
        role: "owner",
      },
    });

    const { container } = render(<DemoBanner />);

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when no user is loaded yet", () => {
    mockUseAuth.mockReturnValue({ user: null, currentMembership: null });

    const { container } = render(<DemoBanner />);

    expect(container).toBeEmptyDOMElement();
  });
});
