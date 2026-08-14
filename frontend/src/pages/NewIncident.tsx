import * as React from "react";
import { useNavigate } from "react-router-dom";

import { AgentPipelineTrace } from "@/components/incidents/AgentPipelineTrace";
import { BriefView } from "@/components/incidents/BriefView";
import { EmptyState } from "@/components/layout/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { createIncident, listBriefs, streamBrief } from "@/lib/api";
import { useAuth, useRequireRole } from "@/lib/auth";
import type { AgentStreamEvent, BriefOut } from "@/lib/types";

const SAMPLE_ALERTS = [
  "checkout-api is returning 500 errors, error rate spiked to 12% starting at 14:32 UTC",
  "Database connection pool exhausted on payments-svc, queries timing out after 30s",
  "Elevated latency on the checkout flow, p99 response time up 4x in the last 10 minutes",
];

const PLACEHOLDER_ALERT = SAMPLE_ALERTS[0];

type Phase = "idle" | "generating" | "done" | "error";

export function NewIncident(): React.JSX.Element {
  const { currentMembership } = useAuth();
  const workspaceId = currentMembership?.workspace_id ?? null;
  const canWrite = useRequireRole("owner", "responder");
  const navigate = useNavigate();

  const [alertText, setAlertText] = React.useState("");
  const [phase, setPhase] = React.useState<Phase>("idle");
  const [events, setEvents] = React.useState<AgentStreamEvent[]>([]);
  const [brief, setBrief] = React.useState<BriefOut | null>(null);
  const [incidentId, setIncidentId] = React.useState<string | null>(null);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const abortRef = React.useRef<(() => void) | null>(null);

  React.useEffect(() => () => abortRef.current?.(), []);

  const submit = async (): Promise<void> => {
    if (!workspaceId || !alertText.trim()) return;
    setPhase("generating");
    setEvents([]);
    setBrief(null);
    setErrorMessage(null);

    let incident: Awaited<ReturnType<typeof createIncident>>;
    try {
      incident = await createIncident(workspaceId, {
        title: alertText.trim().slice(0, 120),
        raw_alert_text: alertText.trim(),
      });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
      setPhase("error");
      return;
    }
    setIncidentId(incident.id);

    abortRef.current = streamBrief(
      workspaceId,
      incident.id,
      (event) => {
        setEvents((prev) => [...prev, event]);
        if (event.type === "done") {
          void listBriefs(workspaceId, incident.id).then((briefs) => {
            setBrief(briefs[0] ?? null);
            setPhase("done");
          });
        } else if (event.type === "error") {
          setErrorMessage(event.message);
          setPhase("error");
        }
      },
      (error) => {
        setErrorMessage(error.message);
        setPhase("error");
      }
    );
  };

  if (!canWrite) {
    return (
      <>
        <PageHeader title="New Incident" />
        <EmptyState
          title="Read-only access"
          description="Ask an owner or responder to file a new incident."
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="New Incident"
        description="Paste an alert and watch the agent pipeline investigate it live."
      />
      <div className="flex flex-col gap-4">
        <Card>
          <CardContent className="flex flex-col gap-3 pt-6">
            <textarea
              value={alertText}
              onChange={(e) => setAlertText(e.target.value)}
              placeholder={PLACEHOLDER_ALERT}
              disabled={phase === "generating"}
              rows={5}
              aria-label="Alert text"
              className="w-full resize-none rounded-md border border-input bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <div className="flex flex-wrap gap-1.5">
              {SAMPLE_ALERTS.map((sample) => (
                <button
                  key={sample}
                  type="button"
                  disabled={phase === "generating"}
                  onClick={() => setAlertText(sample)}
                  className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground hover:bg-muted disabled:opacity-50"
                >
                  {sample.slice(0, 40)}…
                </button>
              ))}
            </div>
            <div>
              <Button
                onClick={() => void submit()}
                disabled={phase === "generating" || !alertText.trim()}
              >
                {phase === "generating" ? "Investigating…" : "Investigate"}
              </Button>
            </div>
          </CardContent>
        </Card>

        {phase === "generating" || phase === "done" ? (
          <Card>
            <CardContent className="pt-6">
              <AgentPipelineTrace events={events} />
            </CardContent>
          </Card>
        ) : null}

        {phase === "error" ? (
          <Card>
            <CardContent className="pt-6 text-sm text-destructive">
              Something went wrong generating this brief: {errorMessage}
            </CardContent>
          </Card>
        ) : null}

        {phase === "done" && brief && workspaceId && incidentId ? (
          <>
            <BriefView brief={brief} workspaceId={workspaceId} incidentId={incidentId} />
            <div>
              <Button variant="outline" onClick={() => navigate(`/incidents/${incidentId}`)}>
                View incident
              </Button>
            </div>
          </>
        ) : null}
      </div>
    </>
  );
}
