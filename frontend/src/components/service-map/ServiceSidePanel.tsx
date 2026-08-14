import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SeverityBadge } from "@/components/ui/severity-badge";
import { StatusPill } from "@/components/ui/status-pill";
import { Timestamp } from "@/components/ui/timestamp";
import { listIncidents } from "@/lib/api";
import type { BlastRadiusOut, IncidentStatus, ServiceOut, TeamOut } from "@/lib/types";

const STATUS_TONE: Record<IncidentStatus, "muted" | "success" | "warning" | "destructive"> = {
  open: "warning",
  mitigated: "muted",
  resolved: "success",
  false_positive: "muted",
};

const TIER_LABEL: Record<number, string> = { 1: "Tier 1", 2: "Tier 2", 3: "Tier 3" };

export function ServiceSidePanel({
  workspaceId,
  service,
  team,
  blastRadius,
  blastRadiusLoading,
  onClose,
}: {
  workspaceId: string;
  service: ServiceOut;
  team: TeamOut | null;
  blastRadius: BlastRadiusOut | undefined;
  blastRadiusLoading: boolean;
  onClose: () => void;
}): React.JSX.Element {
  const incidentsQuery = useQuery({
    queryKey: ["service-incidents", workspaceId, service.id],
    queryFn: () => listIncidents(workspaceId, { service_id: service.id, limit: 5 }),
  });

  return (
    <Card className="flex h-[600px] w-80 shrink-0 flex-col overflow-y-auto">
      <CardHeader className="flex flex-row items-start justify-between gap-2 pb-3">
        <div>
          <CardTitle className="text-base">{service.name}</CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">{TIER_LABEL[service.tier]}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close side panel"
          className="text-muted-foreground hover:text-foreground"
        >
          ✕
        </button>
      </CardHeader>
      <CardContent className="flex flex-col gap-5 text-sm">
        {service.description ? (
          <p className="text-muted-foreground">{service.description}</p>
        ) : null}

        <div>
          <h3 className="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">Owner</h3>
          {team ? (
            <div className="flex flex-col gap-0.5">
              <span>{team.name}</span>
              {team.slack_handle ? (
                <span className="text-xs text-muted-foreground">{team.slack_handle}</span>
              ) : null}
              {team.escalation_contact ? (
                <span className="text-xs text-muted-foreground">{team.escalation_contact}</span>
              ) : null}
            </div>
          ) : (
            <span className="text-muted-foreground">No team assigned</span>
          )}
        </div>

        <div>
          <h3 className="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">Runbook</h3>
          {service.runbook_url ? (
            <a
              href={service.runbook_url}
              target="_blank"
              rel="noreferrer"
              className="text-accent underline"
            >
              {service.runbook_url}
            </a>
          ) : (
            <span className="text-muted-foreground">No runbook linked</span>
          )}
        </div>

        <div>
          <h3 className="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">
            Blast radius
          </h3>
          {blastRadiusLoading ? (
            <span className="text-muted-foreground">Loading…</span>
          ) : blastRadius && blastRadius.services.length > 0 ? (
            <ul className="flex flex-col gap-1">
              {blastRadius.services.map((entry) => (
                <li key={entry.service.id} className="flex items-center justify-between">
                  <span>{entry.service.name}</span>
                  <Badge variant="outline">{Math.round(entry.score * 100)}%</Badge>
                </li>
              ))}
            </ul>
          ) : (
            <span className="text-muted-foreground">No downstream impact</span>
          )}
        </div>

        <div>
          <h3 className="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">
            Incident history
          </h3>
          {incidentsQuery.isLoading ? (
            <span className="text-muted-foreground">Loading…</span>
          ) : incidentsQuery.data && incidentsQuery.data.items.length > 0 ? (
            <ul className="flex flex-col gap-2">
              {incidentsQuery.data.items.map((incident) => (
                <li key={incident.id}>
                  <Link
                    to={`/incidents/${incident.id}`}
                    className="flex flex-col gap-1 rounded-md border border-border p-2 hover:bg-muted"
                  >
                    <span className="font-medium">{incident.title}</span>
                    <div className="flex items-center gap-2">
                      {incident.severity ? <SeverityBadge severity={incident.severity} /> : null}
                      <StatusPill status={incident.status} tone={STATUS_TONE[incident.status]} />
                      <Timestamp value={incident.opened_at} />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <span className="text-muted-foreground">No incidents recorded</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
