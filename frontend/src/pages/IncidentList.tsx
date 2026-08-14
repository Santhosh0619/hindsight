import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import * as React from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/layout/EmptyState";
import { LoadingSkeleton } from "@/components/layout/LoadingSkeleton";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { SeverityBadge } from "@/components/ui/severity-badge";
import { StatusPill } from "@/components/ui/status-pill";
import { Timestamp } from "@/components/ui/timestamp";
import { listIncidents, listServices } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { IncidentOut, IncidentStatus, Severity } from "@/lib/types";

const STATUSES: IncidentStatus[] = ["open", "mitigated", "resolved", "false_positive"];
const SEVERITIES: Severity[] = ["sev1", "sev2", "sev3", "sev4"];
const STATUS_TONE: Record<IncidentStatus, "muted" | "success" | "warning" | "destructive"> = {
  open: "warning",
  mitigated: "muted",
  resolved: "success",
  false_positive: "muted",
};

export function IncidentList(): React.JSX.Element {
  const { currentMembership } = useAuth();
  const workspaceId = currentMembership?.workspace_id ?? null;

  const [status, setStatus] = React.useState<IncidentStatus | "">("");
  const [severity, setSeverity] = React.useState<Severity | "">("");
  const [serviceId, setServiceId] = React.useState("");

  const servicesQuery = useQuery({
    queryKey: ["catalog-services", workspaceId],
    queryFn: () => listServices(workspaceId as string),
    enabled: Boolean(workspaceId),
  });

  // useInfiniteQuery, not a hand-rolled useState+useEffect -- the queryKey already
  // includes every filter, so changing one automatically starts a fresh query at
  // page one instead of appending onto stale results, and loading/error states come
  // from the query itself rather than needing their own hand-tracked booleans.
  const incidentsQuery = useInfiniteQuery({
    queryKey: ["incidents", workspaceId, status, severity, serviceId],
    queryFn: ({ pageParam }) =>
      listIncidents(workspaceId as string, {
        status: status || undefined,
        severity: severity || undefined,
        service_id: serviceId || undefined,
        cursor: pageParam ?? undefined,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
    enabled: Boolean(workspaceId),
  });

  const items: IncidentOut[] = incidentsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const services = servicesQuery.data ?? [];

  return (
    <>
      <PageHeader title="Incidents" description="Every incident filed in this workspace." />
      <div className="mb-4 flex flex-wrap gap-2">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as IncidentStatus | "")}
          aria-label="Filter by status"
          className="rounded-md border border-input bg-transparent px-2 py-1.5 text-sm"
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s.replace("_", " ")}
            </option>
          ))}
        </select>
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value as Severity | "")}
          aria-label="Filter by severity"
          className="rounded-md border border-input bg-transparent px-2 py-1.5 text-sm"
        >
          <option value="">All severities</option>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {s.toUpperCase()}
            </option>
          ))}
        </select>
        <select
          value={serviceId}
          onChange={(e) => setServiceId(e.target.value)}
          aria-label="Filter by service"
          className="rounded-md border border-input bg-transparent px-2 py-1.5 text-sm"
        >
          <option value="">All services</option>
          {services.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </div>

      {incidentsQuery.isLoading ? (
        <LoadingSkeleton lines={5} />
      ) : incidentsQuery.isError ? (
        <EmptyState
          title="Couldn't load incidents"
          description="Something went wrong fetching the list. Try again."
        />
      ) : items.length === 0 ? (
        <EmptyState title="No incidents match these filters" />
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((incident) => (
            <Link key={incident.id} to={`/incidents/${incident.id}`}>
              <Card className="transition-colors hover:bg-muted/50">
                <CardContent className="flex items-center justify-between gap-4 pt-6">
                  <div>
                    <p className="text-sm font-medium">{incident.title}</p>
                    <div className="mt-1 flex items-center gap-2">
                      {incident.severity ? <SeverityBadge severity={incident.severity} /> : null}
                      <Timestamp value={incident.opened_at} />
                    </div>
                  </div>
                  <StatusPill status={incident.status} tone={STATUS_TONE[incident.status]} />
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}

      {incidentsQuery.hasNextPage ? (
        <div className="mt-4">
          <Button
            variant="outline"
            disabled={incidentsQuery.isFetchingNextPage}
            onClick={() => void incidentsQuery.fetchNextPage()}
          >
            Load more
          </Button>
        </div>
      ) : null}
    </>
  );
}
