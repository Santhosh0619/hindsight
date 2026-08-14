import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MttrChart } from "@/components/dashboard/MttrChart";
import type { MttrPointOut } from "@/lib/types";

describe("MttrChart", () => {
  it("shows the empty-data message when every point is null", () => {
    const points: MttrPointOut[] = [
      { week_start: "2026-01-05", mttr_minutes: null },
      { week_start: "2026-01-12", mttr_minutes: null },
    ];
    render(<MttrChart points={points} />);

    expect(screen.getByText("No resolved incidents in the last 8 weeks.")).toBeInTheDocument();
  });

  it("renders a chart when at least one point has data", () => {
    const points: MttrPointOut[] = [
      { week_start: "2026-01-05", mttr_minutes: null },
      { week_start: "2026-01-12", mttr_minutes: 42 },
    ];
    const { container } = render(<MttrChart points={points} />);

    expect(
      screen.queryByText("No resolved incidents in the last 8 weeks.")
    ).not.toBeInTheDocument();
    expect(container.querySelector(".recharts-responsive-container")).toBeInTheDocument();
  });
});
