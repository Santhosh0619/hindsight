import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfidenceBadge } from "@/components/ui/confidence-badge";
import { submitFeedback } from "@/lib/api";
import type { BriefOut, CitationOut, FeedbackVerdict } from "@/lib/types";

function CitationChip({ citation }: { citation: CitationOut }): React.JSX.Element {
  const [open, setOpen] = React.useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="rounded border border-border bg-muted px-2 py-0.5 text-xs font-medium text-foreground hover:bg-accent hover:text-accent-foreground"
      >
        {citation.postmortem_title}
      </button>
      {open ? (
        <p className="mt-1 max-w-md rounded border border-border bg-muted/50 p-2 text-sm text-muted-foreground">
          {citation.content}
        </p>
      ) : null}
    </div>
  );
}

function SubscoreBar({ label, value }: { label: string; value: number }): React.JSX.Element {
  const percent = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-28 shrink-0 text-muted-foreground">{label}</span>
      <div className="h-1.5 flex-1 rounded-full bg-muted">
        <div className="h-1.5 rounded-full bg-accent" style={{ width: `${percent}%` }} />
      </div>
      <span className="w-10 text-right font-mono text-muted-foreground">{percent}%</span>
    </div>
  );
}

const VERDICTS: { value: FeedbackVerdict; label: string }[] = [
  { value: "helpful", label: "Helpful" },
  { value: "partially", label: "Partially" },
  { value: "unhelpful", label: "Unhelpful" },
];

function FeedbackControl({
  workspaceId,
  incidentId,
  briefId,
  candidates,
}: {
  workspaceId: string;
  incidentId: string;
  briefId: string;
  candidates: { id: string; title: string }[];
}): React.JSX.Element {
  const [submitted, setSubmitted] = React.useState<FeedbackVerdict | null>(null);
  const [correctId, setCorrectId] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);

  const submit = async (verdict: FeedbackVerdict): Promise<void> => {
    setSubmitting(true);
    try {
      await submitFeedback(workspaceId, incidentId, briefId, {
        verdict,
        correct_postmortem_id: correctId || undefined,
      });
      setSubmitted(verdict);
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return <p className="text-sm text-muted-foreground">Thanks for the feedback.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-2">
        {VERDICTS.map((v) => (
          <Button
            key={v.value}
            variant="outline"
            size="sm"
            disabled={submitting}
            onClick={() => void submit(v.value)}
          >
            {v.label}
          </Button>
        ))}
      </div>
      {candidates.length > 0 ? (
        <select
          value={correctId}
          onChange={(e) => setCorrectId(e.target.value)}
          aria-label="The correct match was"
          className="w-fit rounded-md border border-input bg-transparent px-2 py-1.5 text-sm"
        >
          <option value="">The correct match was…</option>
          {candidates.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title}
            </option>
          ))}
        </select>
      ) : null}
    </div>
  );
}

export function BriefView({
  brief,
  workspaceId,
  incidentId,
}: {
  brief: BriefOut;
  workspaceId: string;
  incidentId: string;
}): React.JSX.Element {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-1.5">
        {brief.from_cache ? <Badge variant="muted">served from cache</Badge> : null}
        {!brief.llm_used ? <Badge variant="warning">generated without LLM</Badge> : null}
        {brief.correction_passes > 0 ? (
          <Badge variant="outline">
            {brief.correction_passes} correction pass{brief.correction_passes > 1 ? "es" : ""}
          </Badge>
        ) : null}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Hypotheses</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {brief.hypotheses.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {brief.llm_used
                ? "No hypotheses were generated for this incident."
                : "No hypotheses — this brief is deterministic-only."}
            </p>
          ) : (
            brief.hypotheses.map((h, i) => (
              <div key={i} className="flex flex-col gap-1.5">
                <div className="flex items-center gap-2">
                  <ConfidenceBadge confidence={h.confidence} />
                  <p className="text-sm">{h.statement}</p>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {h.citations.map((c, j) => (
                    <CitationChip key={j} citation={c} />
                  ))}
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Matched prior incidents</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {brief.matched_postmortems.length === 0 ? (
            <p className="text-sm text-muted-foreground">No matches found in the corpus.</p>
          ) : (
            brief.matched_postmortems.map((m) => (
              <div
                key={m.postmortem.id}
                className="flex flex-col gap-1.5 border-b border-border pb-3 last:border-0 last:pb-0"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium">{m.postmortem.title}</p>
                  <Badge variant="outline">#{m.rank}</Badge>
                </div>
                <div className="grid gap-1">
                  <SubscoreBar label="Vector" value={m.vector_score} />
                  <SubscoreBar label="Keyword" value={m.keyword_score} />
                  <SubscoreBar label="Graph" value={m.graph_score} />
                  <SubscoreBar label="Failure mode" value={m.failure_mode_overlap} />
                  <SubscoreBar label="Recency" value={m.recency} />
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Blast radius</CardTitle>
        </CardHeader>
        <CardContent>
          {brief.blast_radius.services.length === 0 ? (
            <p className="text-sm text-muted-foreground">No downstream impact computed.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {brief.blast_radius.services.map((entry) => (
                <li key={entry.service.id} className="flex items-center justify-between text-sm">
                  <span>
                    {entry.service.name}{" "}
                    <span className="text-muted-foreground">
                      (tier {entry.service.tier}
                      {entry.path.length > 1
                        ? `, via ${entry.path.map((s) => s.name).join(" → ")}`
                        : ""}
                      )
                    </span>
                  </span>
                  <Badge variant="outline">{Math.round(entry.score * 100)}%</Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Runbook</CardTitle>
        </CardHeader>
        <CardContent>
          {brief.runbook_steps.length === 0 ? (
            <p className="text-sm text-muted-foreground">No runbook steps assembled.</p>
          ) : (
            <ol className="flex flex-col gap-2">
              {brief.runbook_steps.map((s, i) => (
                <li key={i} className="flex flex-col gap-1 text-sm">
                  <span>
                    {i + 1}. {s.step}
                  </span>
                  {s.citation ? <CitationChip citation={s.citation} /> : null}
                </li>
              ))}
            </ol>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Feedback</CardTitle>
        </CardHeader>
        <CardContent>
          <FeedbackControl
            workspaceId={workspaceId}
            incidentId={incidentId}
            briefId={brief.id}
            candidates={brief.matched_postmortems.map((m) => ({
              id: m.postmortem.id,
              title: m.postmortem.title,
            }))}
          />
        </CardContent>
      </Card>
    </div>
  );
}
