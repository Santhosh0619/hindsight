import { useQuery } from "@tanstack/react-query";
import * as React from "react";
import { useParams } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusPill } from "@/components/ui/status-pill";
import { EmptyState } from "@/components/layout/EmptyState";
import { LoadingSkeleton } from "@/components/layout/LoadingSkeleton";
import { PageHeader } from "@/components/layout/PageHeader";
import { getPostmortem } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { buildHighlightSegments } from "@/lib/highlight-text";
import type { FactType, PostmortemStatus } from "@/lib/types";

const STATUS_TONE: Record<PostmortemStatus, "muted" | "success" | "warning" | "destructive"> = {
  pending: "muted",
  processing: "warning",
  indexed: "success",
  failed: "destructive",
};

const FACT_TYPE_LABEL: Record<FactType, string> = {
  trigger: "Trigger",
  root_cause: "Root cause",
  remediation: "Remediation",
  detection_gap: "Detection gap",
  contributing_factor: "Contributing factor",
};

const FACT_TYPE_MARK_CLASS: Record<FactType, string> = {
  trigger: "bg-warning/25",
  root_cause: "bg-destructive/25",
  remediation: "bg-success/25",
  detection_gap: "bg-accent/25",
  contributing_factor: "bg-muted",
};

export function PostmortemDetail(): React.JSX.Element {
  const { id } = useParams<{ id: string }>();
  const { currentMembership } = useAuth();
  const workspaceId = currentMembership?.workspace_id ?? null;

  const detailQuery = useQuery({
    queryKey: ["postmortem", workspaceId, id],
    queryFn: () => getPostmortem(workspaceId as string, id as string),
    enabled: Boolean(workspaceId) && Boolean(id),
  });

  if (!workspaceId || !id || detailQuery.isLoading) {
    return <LoadingSkeleton lines={6} />;
  }
  if (detailQuery.isError) {
    return (
      <EmptyState
        title="Couldn't load this postmortem"
        description="Something went wrong fetching it. Try refreshing the page."
      />
    );
  }

  const postmortem = detailQuery.data;
  if (!postmortem) {
    return <EmptyState title="Postmortem not found" />;
  }

  const segments =
    postmortem.redacted_text !== null
      ? buildHighlightSegments(postmortem.redacted_text, postmortem.facts)
      : [];

  return (
    <>
      <PageHeader title={postmortem.title} />
      <div className="mb-4 flex items-center gap-2">
        <StatusPill status={postmortem.status} tone={STATUS_TONE[postmortem.status]} />
        {postmortem.severity ? (
          <Badge variant="outline">{postmortem.severity.toUpperCase()}</Badge>
        ) : null}
      </div>

      {postmortem.injection_flagged ? (
        <Card className="mb-4 border-destructive/40">
          <CardContent className="pt-6 text-sm text-destructive">
            This document contained a suspected prompt-injection attempt. It was processed as
            untrusted content and never given tool access — nothing in it was treated as an
            instruction.
          </CardContent>
        </Card>
      ) : null}

      {postmortem.affected_services.length > 0 ? (
        <div className="mb-4 flex flex-wrap gap-1.5">
          {postmortem.affected_services.map((link) => (
            <Badge key={link.service.id} variant="muted">
              {link.service.name} ({link.role.replace("_", " ")})
            </Badge>
          ))}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Document</CardTitle>
          </CardHeader>
          <CardContent>
            {postmortem.redacted_text === null ? (
              <p className="text-sm text-muted-foreground">
                Still {postmortem.status === "failed" ? "failed to process" : "processing"} — the
                document isn't available yet.
              </p>
            ) : (
              <p className="whitespace-pre-wrap text-sm leading-relaxed">
                {segments.map((segment, index) =>
                  segment.factType ? (
                    <mark
                      key={index}
                      className={FACT_TYPE_MARK_CLASS[segment.factType]}
                      title={FACT_TYPE_LABEL[segment.factType]}
                    >
                      {segment.text}
                    </mark>
                  ) : (
                    <React.Fragment key={index}>{segment.text}</React.Fragment>
                  )
                )}
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Extracted facts</CardTitle>
          </CardHeader>
          <CardContent>
            {postmortem.facts.length === 0 ? (
              <p className="text-sm text-muted-foreground">No facts extracted yet.</p>
            ) : (
              <ul className="flex flex-col gap-3">
                {postmortem.facts.map((fact, index) => (
                  <li key={index} className="text-sm">
                    <Badge variant="outline" className="mb-1">
                      {FACT_TYPE_LABEL[fact.fact_type]}
                    </Badge>
                    <p>{fact.statement}</p>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
