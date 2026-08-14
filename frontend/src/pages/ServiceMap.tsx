import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { ServiceMapCanvas } from "@/components/service-map/ServiceMapCanvas";
import { ServiceSidePanel } from "@/components/service-map/ServiceSidePanel";
import { EmptyState } from "@/components/layout/EmptyState";
import { LoadingSkeleton } from "@/components/layout/LoadingSkeleton";
import { PageHeader } from "@/components/layout/PageHeader";
import { getBlastRadius, getGraph, listTeams } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function ServiceMap(): React.JSX.Element {
  const { currentMembership } = useAuth();
  const workspaceId = currentMembership?.workspace_id ?? null;

  const [selectedServiceId, setSelectedServiceId] = React.useState<string | null>(null);
  const [teamFilter, setTeamFilter] = React.useState("");
  const [search, setSearch] = React.useState("");

  const graphQuery = useQuery({
    queryKey: ["catalog-graph", workspaceId],
    queryFn: () => getGraph(workspaceId as string),
    enabled: Boolean(workspaceId),
  });
  const teamsQuery = useQuery({
    queryKey: ["catalog-teams", workspaceId],
    queryFn: () => listTeams(workspaceId as string),
    enabled: Boolean(workspaceId),
  });
  const blastRadiusQuery = useQuery({
    queryKey: ["service-blast-radius", workspaceId, selectedServiceId],
    queryFn: () => getBlastRadius(workspaceId as string, selectedServiceId as string),
    enabled: Boolean(workspaceId) && Boolean(selectedServiceId),
  });

  const nodes = graphQuery.data?.nodes ?? [];
  const edges = graphQuery.data?.edges ?? [];
  const teams = teamsQuery.data ?? [];

  const filteredNodes = nodes.filter((node) => {
    if (teamFilter && node.team_id !== teamFilter) return false;
    if (search && !node.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });
  const filteredIds = new Set(filteredNodes.map((n) => n.id));
  const filteredEdges = edges.filter(
    (edge) => filteredIds.has(edge.from_service_id) && filteredIds.has(edge.to_service_id)
  );

  const selectedService = nodes.find((n) => n.id === selectedServiceId) ?? null;
  const selectedTeam = selectedService
    ? (teams.find((t) => t.id === selectedService.team_id) ?? null)
    : null;
  const highlightedServiceIds = new Set<string>(
    selectedService
      ? [selectedService.id, ...(blastRadiusQuery.data?.services.map((e) => e.service.id) ?? [])]
      : []
  );

  if (!workspaceId || graphQuery.isLoading || teamsQuery.isLoading) {
    return <LoadingSkeleton lines={8} />;
  }

  return (
    <>
      <PageHeader
        title="Service Map"
        description="The dependency graph behind every blast-radius score."
      />
      {graphQuery.isError || teamsQuery.isError ? (
        <EmptyState
          title="Couldn't load the service map"
          description="Something went wrong fetching the catalog. Try again."
        />
      ) : nodes.length === 0 ? (
        <EmptyState
          title="No services yet"
          description="Add services and dependencies from the catalog to see them here."
        />
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-2">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name"
              aria-label="Search services by name"
              className="rounded-md border border-input bg-transparent px-2 py-1.5 text-sm"
            />
            <select
              value={teamFilter}
              onChange={(e) => setTeamFilter(e.target.value)}
              aria-label="Filter by team"
              className="rounded-md border border-input bg-transparent px-2 py-1.5 text-sm"
            >
              <option value="">All teams</option>
              {teams.map((team) => (
                <option key={team.id} value={team.id}>
                  {team.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex gap-4">
            <div className="min-w-0 flex-1">
              <ServiceMapCanvas
                nodes={filteredNodes}
                edges={filteredEdges}
                teams={teams}
                selectedServiceId={selectedServiceId}
                highlightedServiceIds={highlightedServiceIds}
                onSelectService={setSelectedServiceId}
              />
            </div>
            {selectedService && workspaceId ? (
              <ServiceSidePanel
                workspaceId={workspaceId}
                service={selectedService}
                team={selectedTeam}
                blastRadius={blastRadiusQuery.data}
                blastRadiusLoading={blastRadiusQuery.isLoading}
                blastRadiusError={blastRadiusQuery.isError}
                onClose={() => setSelectedServiceId(null)}
              />
            ) : null}
          </div>
        </div>
      )}
    </>
  );
}
