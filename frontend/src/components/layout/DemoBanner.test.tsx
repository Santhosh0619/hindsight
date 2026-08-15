import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DemoBanner } from "@/components/layout/DemoBanner";

const mockUseAuth = vi.fn();

vi.mock("@/lib/auth", () => ({
  useAuth: () => mockUseAuth(),
}));

describe("DemoBanner", () => {
  it("renders the synthetic-data notice for a demo guest", () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: "1",
        email: "guest@demo.hindsight.local",
        full_name: "Demo Guest",
        is_demo: true,
      },
    });

    render(<DemoBanner />);

    expect(screen.getByText(/demo workspace.*synthetic data.*read-only/i)).toBeInTheDocument();
  });

  it("renders nothing for a real (non-demo) user", () => {
    mockUseAuth.mockReturnValue({
      user: { id: "2", email: "owner@example.com", full_name: "Owner User", is_demo: false },
    });

    const { container } = render(<DemoBanner />);

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when no user is loaded yet", () => {
    mockUseAuth.mockReturnValue({ user: null });

    const { container } = render(<DemoBanner />);

    expect(container).toBeEmptyDOMElement();
  });
});
