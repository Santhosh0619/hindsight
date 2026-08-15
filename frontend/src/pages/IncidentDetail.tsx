import * as React from "react";
import { useParams } from "react-router-dom";

import { AgentPipelineTrace } from "@/components/incidents/AgentPipelineTrace";
import { BriefView } from "@/components/incidents/BriefView";
import { EmptyState } from "@/components/layout/EmptyState";
import { LoadingSkeleton } from "@/components/layout/LoadingSkeleton";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { StatusPill } from "@/components/ui/status-pill";
import { getIncident, listBriefs, streamBrief } from "@/lib/api";
import { useAuth, useCanGenerateBrief } from "@/lib/auth";
import type { AgentStreamEvent, BriefOut, IncidentOut, IncidentStatus } from "@/lib/types";

const STATUS_TONE: Record<IncidentStatus, "muted" | "success" | "warning" | "destructive"> = {
  open: "warning",
  mitigated: "muted",
  resolved: "success",
  false_positive: "muted",
};

export function IncidentDetail(): React.JSX.Element {
  const { id } = useParams<{ id: string }>();
  const { currentMembership } = useAuth();
  const workspaceId = currentMembership?.workspace_id ?? null;
  const canGenerateBrief = useCanGenerateBrief();

  const [incident, setIncident] = React.useState<IncidentOut | null>(null);
  const [brief, setBrief] = React.useState<BriefOut | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [loadError, setLoadError] = React.useState(false);
  const [generating, setGenerating] = React.useState(false);
  const [events, setEvents] = React.useState<AgentStreamEvent[]>([]);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const abortRef = React.useRef<(() => void) | null>(null);

  const load = React.useCallback(async () => {
    if (!workspaceId || !id) return;
    setLoading(true);
    setLoadError(false);
    try {
      const [incidentData, briefs] = await Promise.all([
        getIncident(workspaceId, id),
        listBriefs(workspaceId, id),
      ]);
      setIncident(incidentData);
      setBrief(briefs[0] ?? null);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, id]);

  React.useEffect(() => {
    void load();
  }, [load]);

  React.useEffect(() => () => abortRef.current?.(), []);

  const generate = (): void => {
    if (!workspaceId || !id) return;
    setGenerating(true);
    setEvents([]);
    setErrorMessage(null);
    abortRef.current = streamBrief(
      workspaceId,
      id,
      (event) => {
        setEvents((prev) => [...prev, event]);
        if (event.type === "done") {
          setGenerating(false);
          void load();
        } else if (event.type === "error") {
          setErrorMessage(event.message);
          setGenerating(false);
        }
      },
      (error) => {
        setErrorMessage(error.message);
        setGenerating(false);
      }
    );
  };

  if (!workspaceId || !id || loading) {
    return <LoadingSkeleton lines={6} />;
  }
  if (loadError) {
    return (
      <EmptyState
        title="Couldn't load this incident"
        description="Something went wrong fetching it. Try refreshing the page."
      />
    );
  }
  if (!incident) {
    return <EmptyState title="Incident not found" />;
  }

  return (
    <>
      <PageHeader
        title={incident.title}
        description={incident.raw_alert_text}
        actions={
          canGenerateBrief ? (
            <Button onClick={generate} disabled={generating}>
              {generating ? "Generating…" : brief ? "Regenerate brief" : "Generate brief"}
            </Button>
          ) : undefined
        }
      />
      <div className="mb-4">
        <StatusPill status={incident.status} tone={STATUS_TONE[incident.status]} />
      </div>

      {generating ? (
        <Card className="mb-4">
          <CardContent className="pt-6">
            <AgentPipelineTrace events={events} />
          </CardContent>
        </Card>
      ) : null}

      {errorMessage ? (
        <Card className="mb-4">
          <CardContent className="pt-6 text-sm text-destructive">{errorMessage}</CardContent>
        </Card>
      ) : null}

      {brief ? (
        <BriefView brief={brief} workspaceId={workspaceId} incidentId={id} />
      ) : !generating ? (
        <EmptyState
          title="No brief yet"
          description={
            canGenerateBrief
              ? "Generate one to see hypotheses, citations, and blast radius."
              : "Ask an owner or responder to generate one."
          }
        />
      ) : null}
    </>
  );
}
