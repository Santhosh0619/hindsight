import { useInfiniteQuery } from "@tanstack/react-query";
import * as React from "react";
import { Link } from "react-router-dom";

import { NewPostmortemModal } from "@/components/knowledge-base/NewPostmortemModal";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { StatusPill } from "@/components/ui/status-pill";
import { Timestamp } from "@/components/ui/timestamp";
import { EmptyState } from "@/components/layout/EmptyState";
import { LoadingSkeleton } from "@/components/layout/LoadingSkeleton";
import { PageHeader } from "@/components/layout/PageHeader";
import { listPostmortems } from "@/lib/api";
import { useAuth, useRequireRole } from "@/lib/auth";
import type { PostmortemStatus } from "@/lib/types";

const STATUSES: PostmortemStatus[] = ["pending", "processing", "indexed", "failed"];
const STATUS_TONE: Record<PostmortemStatus, "muted" | "success" | "warning" | "destructive"> = {
  pending: "muted",
  processing: "warning",
  indexed: "success",
  failed: "destructive",
};

export function KnowledgeBase(): React.JSX.Element {
  const { currentMembership } = useAuth();
  const workspaceId = currentMembership?.workspace_id ?? null;
  const canWrite = useRequireRole("owner", "responder");

  const [status, setStatus] = React.useState<PostmortemStatus | "">("");
  const [modalOpen, setModalOpen] = React.useState(false);

  const postmortemsQuery = useInfiniteQuery({
    queryKey: ["postmortems", workspaceId, status],
    queryFn: ({ pageParam }) =>
      listPostmortems(workspaceId as string, {
        status: status || undefined,
        cursor: pageParam ?? undefined,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
    enabled: Boolean(workspaceId),
  });

  const items = postmortemsQuery.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <>
      <PageHeader
        title="Knowledge Base"
        description="Every postmortem ingested into this workspace's corpus."
        actions={
          canWrite ? <Button onClick={() => setModalOpen(true)}>New postmortem</Button> : undefined
        }
      />

      <div className="mb-4">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as PostmortemStatus | "")}
          aria-label="Filter by status"
          className="rounded-md border border-input bg-transparent px-2 py-1.5 text-sm"
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {!workspaceId || postmortemsQuery.isLoading ? (
        <LoadingSkeleton lines={5} />
      ) : postmortemsQuery.isError ? (
        <EmptyState
          title="Couldn't load the knowledge base"
          description="Something went wrong fetching postmortems. Try again."
        />
      ) : items.length === 0 ? (
        <EmptyState
          title="No postmortems yet"
          description={
            canWrite
              ? "Ingest one to start building the corpus."
              : "Ask an owner or responder to ingest one."
          }
        />
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((postmortem) => (
            <Link key={postmortem.id} to={`/knowledge-base/${postmortem.id}`}>
              <Card className="transition-colors hover:bg-muted/50">
                <CardContent className="flex items-center justify-between gap-4 pt-6">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{postmortem.title}</p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2">
                      <StatusPill
                        status={postmortem.status}
                        tone={STATUS_TONE[postmortem.status]}
                      />
                      {postmortem.severity ? (
                        <Badge variant="outline">{postmortem.severity.toUpperCase()}</Badge>
                      ) : null}
                      {postmortem.injection_flagged ? (
                        <Badge variant="warning">injection flagged</Badge>
                      ) : null}
                      <Timestamp value={postmortem.occurred_at ?? postmortem.created_at} />
                    </div>
                    {postmortem.affected_services.length > 0 ? (
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {postmortem.affected_services.map((link) => (
                          <Badge key={link.service.id} variant="muted">
                            {link.service.name}
                          </Badge>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}

      {postmortemsQuery.hasNextPage ? (
        <div className="mt-4">
          <Button
            variant="outline"
            disabled={postmortemsQuery.isFetchingNextPage}
            onClick={() => void postmortemsQuery.fetchNextPage()}
          >
            Load more
          </Button>
        </div>
      ) : null}

      {workspaceId ? (
        <NewPostmortemModal
          workspaceId={workspaceId}
          open={modalOpen}
          onOpenChange={setModalOpen}
          onIngested={() => void postmortemsQuery.refetch()}
        />
      ) : null}
    </>
  );
}
