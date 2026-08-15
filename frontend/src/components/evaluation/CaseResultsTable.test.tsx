import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CaseResultsTable } from "@/components/evaluation/CaseResultsTable";
import type { EvalCaseResultOut } from "@/lib/types";

function result(overrides: Partial<EvalCaseResultOut>): EvalCaseResultOut {
  return {
    id: "result-id",
    eval_case_id: "case-id",
    case_name: "case",
    retrieved_ids: [],
    rank_of_first_hit: 1,
    groundedness: null,
    passed: true,
    ...overrides,
  };
}

describe("CaseResultsTable", () => {
  it("sorts failing cases before passing ones", () => {
    const results: EvalCaseResultOut[] = [
      result({ id: "a", case_name: "passing-case", passed: true }),
      result({ id: "b", case_name: "failing-case", passed: false, rank_of_first_hit: null }),
    ];
    render(<CaseResultsTable results={results} />);

    const [firstRow, secondRow] = screen.getAllByRole("row").slice(1); // drop the header row
    expect(firstRow?.textContent).toContain("failing-case");
    expect(secondRow?.textContent).toContain("passing-case");
  });

  it("shows 'not retrieved' for a case with no rank, not a raw null", () => {
    const results: EvalCaseResultOut[] = [
      result({ case_name: "miss", rank_of_first_hit: null, passed: false }),
    ];
    render(<CaseResultsTable results={results} />);

    expect(screen.getByText("not retrieved")).toBeInTheDocument();
  });

  it("shows an empty-state message with no results", () => {
    render(<CaseResultsTable results={[]} />);

    expect(screen.getByText("No case results for this run.")).toBeInTheDocument();
  });
});
