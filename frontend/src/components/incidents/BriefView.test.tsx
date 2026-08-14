import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { BriefView } from "@/components/incidents/BriefView";
import type { BriefOut } from "@/lib/types";

const mockSubmitFeedback = vi.fn();
vi.mock("@/lib/api", () => ({
  submitFeedback: (...args: unknown[]) => mockSubmitFeedback(...args),
}));

const POSTMORTEM = {
  id: "pm-1",
  external_ref: null,
  title: "Checkout outage",
  occurred_at: null,
  duration_minutes: null,
  severity: "sev2" as const,
  status: "indexed" as const,
  injection_flagged: false,
  failure_reason: null,
  created_at: "2026-01-01T00:00:00Z",
};

const CITATION = {
  chunk_id: "chunk-1",
  postmortem_id: "pm-1",
  postmortem_title: "Checkout outage",
  quote: null,
  content: "The connection pool was exhausted during peak traffic.",
  char_start: 0,
  char_end: 55,
};

const BASE_BRIEF: BriefOut = {
  id: "brief-1",
  incident_id: "incident-1",
  version: 1,
  hypotheses: [
    {
      statement: "Connection pool exhaustion caused the outage",
      confidence: 0.82,
      citations: [CITATION],
    },
  ],
  matched_postmortems: [
    {
      postmortem: POSTMORTEM,
      vector_score: 0.8,
      keyword_score: 0.5,
      graph_score: 0.0,
      failure_mode_overlap: 0.6,
      recency: 1.0,
      overall_score: 0.58,
      rank: 1,
    },
  ],
  blast_radius: {
    services: [
      {
        service: {
          id: "svc-1",
          name: "payments-svc",
          tier: 1,
          team_id: null,
          repo_url: null,
          description: null,
          runbook_url: null,
        },
        score: 0.7,
        path: [
          {
            id: "svc-0",
            name: "checkout-api",
            tier: 1,
            team_id: null,
            repo_url: null,
            description: null,
            runbook_url: null,
          },
          {
            id: "svc-1",
            name: "payments-svc",
            tier: 1,
            team_id: null,
            repo_url: null,
            description: null,
            runbook_url: null,
          },
        ],
        depth: 1,
      },
    ],
  },
  runbook_steps: [
    { step: "Restart the pool manager", source_postmortem_id: "pm-1", citation: CITATION },
  ],
  citations: [CITATION],
  overall_confidence: 0.82,
  correction_passes: 0,
  llm_used: true,
  from_cache: false,
  generated_at: "2026-01-01T00:05:00Z",
};

describe("BriefView", () => {
  it("renders hypotheses, matched postmortems with subscores, blast radius, and runbook", () => {
    render(<BriefView brief={BASE_BRIEF} workspaceId="ws-1" incidentId="incident-1" />);

    expect(screen.getByText("Connection pool exhaustion caused the outage")).toBeInTheDocument();
    expect(screen.getByText("82%")).toBeInTheDocument(); // ConfidenceBadge
    // Renders in multiple places: the citation chip, the matched-postmortem card, the
    // runbook step's citation chip, and the feedback dropdown's option.
    expect(screen.getAllByText("Checkout outage").length).toBeGreaterThanOrEqual(2);
    // The blast radius entry's text is split across nested spans (name, tier, path),
    // so match on the containing list item rather than an ambiguous text fragment --
    // the runbook's <ol> also has "listitem" roles, so find the one that's ours.
    const blastRadiusEntry = screen
      .getAllByRole("listitem")
      .find((el) => el.textContent?.includes("payments-svc"));
    expect(blastRadiusEntry?.textContent).toContain("tier 1");
    expect(blastRadiusEntry?.textContent).toContain("checkout-api → payments-svc");
    expect(screen.getByText(/Restart the pool manager/)).toBeInTheDocument();
  });

  it("shows a citation's grounding excerpt only after clicking the chip", async () => {
    const user = userEvent.setup();
    render(<BriefView brief={BASE_BRIEF} workspaceId="ws-1" incidentId="incident-1" />);

    expect(
      screen.queryByText("The connection pool was exhausted during peak traffic.")
    ).not.toBeInTheDocument();

    const [firstCitationChip] = screen.getAllByText("Checkout outage");
    await user.click(firstCitationChip as HTMLElement);

    expect(
      screen.getByText("The connection pool was exhausted during peak traffic.")
    ).toBeInTheDocument();
  });

  it("shows badges only when their condition is true", () => {
    const { rerender } = render(
      <BriefView brief={BASE_BRIEF} workspaceId="ws-1" incidentId="incident-1" />
    );
    expect(screen.queryByText("served from cache")).not.toBeInTheDocument();
    expect(screen.queryByText("generated without LLM")).not.toBeInTheDocument();

    rerender(
      <BriefView
        brief={{ ...BASE_BRIEF, from_cache: true, llm_used: false, correction_passes: 2 }}
        workspaceId="ws-1"
        incidentId="incident-1"
      />
    );
    expect(screen.getByText("served from cache")).toBeInTheDocument();
    expect(screen.getByText("generated without LLM")).toBeInTheDocument();
    expect(screen.getByText("2 correction passes")).toBeInTheDocument();
  });

  it("submits feedback with the selected verdict and correct-match id", async () => {
    const user = userEvent.setup();
    mockSubmitFeedback.mockResolvedValue({});
    render(<BriefView brief={BASE_BRIEF} workspaceId="ws-1" incidentId="incident-1" />);

    await user.selectOptions(screen.getByLabelText("The correct match was"), "pm-1");
    await user.click(screen.getByRole("button", { name: "Helpful" }));

    expect(mockSubmitFeedback).toHaveBeenCalledWith("ws-1", "incident-1", "brief-1", {
      verdict: "helpful",
      correct_postmortem_id: "pm-1",
    });
    expect(await screen.findByText("Thanks for the feedback.")).toBeInTheDocument();
  });

  it("shows deterministic-only empty states when nothing was generated", () => {
    render(
      <BriefView
        brief={{
          ...BASE_BRIEF,
          hypotheses: [],
          matched_postmortems: [],
          blast_radius: { services: [] },
          runbook_steps: [],
        }}
        workspaceId="ws-1"
        incidentId="incident-1"
      />
    );

    expect(
      screen.getByText("No hypotheses — this brief is deterministic-only.")
    ).toBeInTheDocument();
    expect(screen.getByText("No matches found in the corpus.")).toBeInTheDocument();
    expect(screen.getByText("No downstream impact computed.")).toBeInTheDocument();
    expect(screen.getByText("No runbook steps assembled.")).toBeInTheDocument();
  });
});
