import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import * as React from "react";

import { EmptyState } from "@/components/layout/EmptyState";
import { LoadingSkeleton } from "@/components/layout/LoadingSkeleton";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Timestamp } from "@/components/ui/timestamp";
import { getAuditLog, listMembers } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function AuditLog(): React.JSX.Element {
  const { currentMembership } = useAuth();
  const workspaceId = currentMembership?.workspace_id ?? null;

  const [actorUserId, setActorUserId] = React.useState("");
  const [action, setAction] = React.useState("");
  const [targetType, setTargetType] = React.useState("");

  const membersQuery = useQuery({
    queryKey: ["members", workspaceId],
    queryFn: () => listMembers(workspaceId as string),
    enabled: Boolean(workspaceId),
  });

  const auditQuery = useInfiniteQuery({
    queryKey: ["audit-log", workspaceId, actorUserId, action, targetType],
    queryFn: ({ pageParam }) =>
      getAuditLog(workspaceId as string, {
        cursor: pageParam ?? undefined,
        actor_user_id: actorUserId || undefined,
        action: action || undefined,
        target_type: targetType || undefined,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
    enabled: Boolean(workspaceId),
  });

  const entries = auditQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const members = membersQuery.data ?? [];

  return (
    <>
      <PageHeader
        title="Audit Log"
        description="Every write action taken in this workspace, newest first."
      />

      <div className="mb-4 flex flex-wrap gap-2">
        <select
          value={actorUserId}
          onChange={(e) => setActorUserId(e.target.value)}
          aria-label="Filter by actor"
          className="rounded-md border border-input bg-transparent px-2 py-1.5 text-sm"
        >
          <option value="">All actors</option>
          {members.map((member) => (
            <option key={member.user_id} value={member.user_id}>
              {member.full_name}
            </option>
          ))}
        </select>
        <input
          value={action}
          onChange={(e) => setAction(e.target.value)}
          placeholder="Action (e.g. api_key.created)"
          aria-label="Filter by action"
          className="rounded-md border border-input bg-transparent px-2 py-1.5 text-sm placeholder:text-muted-foreground"
        />
        <input
          value={targetType}
          onChange={(e) => setTargetType(e.target.value)}
          placeholder="Target type (e.g. api_key)"
          aria-label="Filter by target type"
          className="rounded-md border border-input bg-transparent px-2 py-1.5 text-sm placeholder:text-muted-foreground"
        />
      </div>

      {!workspaceId || auditQuery.isLoading ? (
        <LoadingSkeleton lines={6} />
      ) : auditQuery.isError ? (
        <EmptyState
          title="Couldn't load the audit log"
          description="Something went wrong fetching audit log entries. Try again."
        />
      ) : entries.length === 0 ? (
        <EmptyState
          title="No matching entries"
          description="Nothing has been logged yet for this filter."
        />
      ) : (
        <div className="flex flex-col gap-2">
          {entries.map((entry) => (
            <Card key={entry.id}>
              <CardContent className="flex items-center justify-between gap-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{entry.action}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {entry.target_type}
                    {entry.target_id ? ` · ${entry.target_id}` : ""}
                  </p>
                </div>
                <Timestamp value={entry.created_at} />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {auditQuery.hasNextPage ? (
        <div className="mt-4">
          <Button
            variant="outline"
            disabled={auditQuery.isFetchingNextPage}
            onClick={() => void auditQuery.fetchNextPage()}
          >
            Load more
          </Button>
        </div>
      ) : null}
    </>
  );
}
