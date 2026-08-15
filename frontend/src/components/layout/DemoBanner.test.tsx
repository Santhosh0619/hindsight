import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DemoBanner } from "@/components/layout/DemoBanner";

const mockUseIsDemoWorkspace = vi.fn();

vi.mock("@/lib/auth", () => ({
  useIsDemoWorkspace: () => mockUseIsDemoWorkspace(),
}));

describe("DemoBanner", () => {
  it("renders the synthetic-data notice when viewing the demo workspace", () => {
    mockUseIsDemoWorkspace.mockReturnValue(true);

    render(<DemoBanner />);

    expect(screen.getByText(/demo workspace.*synthetic data.*read-only/i)).toBeInTheDocument();
  });

  it("renders nothing otherwise", () => {
    // Covers both a real (non-demo) user and a demo guest viewing a real workspace
    // they've also joined -- useIsDemoWorkspace is the single source of truth for
    // that distinction (frontend/src/lib/auth.tsx), so DemoBanner has nothing left
    // to get wrong here beyond trusting its return value.
    mockUseIsDemoWorkspace.mockReturnValue(false);

    const { container } = render(<DemoBanner />);

    expect(container).toBeEmptyDOMElement();
  });
});
