import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusPill } from "@/components/ui/status-pill";
import { createPostmortem, getPostmortemStatus } from "@/lib/api";
import type { PostmortemStatus } from "@/lib/types";

const STATUS_TONE: Record<PostmortemStatus, "muted" | "success" | "warning" | "destructive"> = {
  pending: "muted",
  processing: "warning",
  indexed: "success",
  failed: "destructive",
};

const TERMINAL_STATUSES = new Set<PostmortemStatus>(["indexed", "failed"]);

export function NewPostmortemModal({
  workspaceId,
  open,
  onOpenChange,
  onIngested,
}: {
  workspaceId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onIngested: () => void;
}): React.JSX.Element {
  const queryClient = useQueryClient();
  const [title, setTitle] = React.useState("");
  const [rawText, setRawText] = React.useState("");
  const [postmortemId, setPostmortemId] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const statusQuery = useQuery({
    queryKey: ["postmortem-status", workspaceId, postmortemId],
    queryFn: () => getPostmortemStatus(workspaceId, postmortemId as string),
    enabled: Boolean(postmortemId),
    refetchInterval: (query) =>
      query.state.data && TERMINAL_STATUSES.has(query.state.data.status) ? false : 1000,
  });

  React.useEffect(() => {
    if (statusQuery.data?.status === "indexed") {
      void queryClient.invalidateQueries({ queryKey: ["postmortems", workspaceId] });
      onIngested();
    }
  }, [statusQuery.data?.status, queryClient, workspaceId, onIngested]);

  const reset = (): void => {
    setTitle("");
    setRawText("");
    setPostmortemId(null);
    setErrorMessage(null);
  };

  const submit = async (): Promise<void> => {
    if (!title.trim() || !rawText.trim()) return;
    setSubmitting(true);
    setErrorMessage(null);
    try {
      const postmortem = await createPostmortem(workspaceId, {
        title: title.trim(),
        raw_text: rawText.trim(),
      });
      setPostmortemId(postmortem.id);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) reset();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New postmortem</DialogTitle>
          <DialogDescription>
            Paste a postmortem document. It's redacted, chunked, and indexed in the background —
            this stays open so you can watch it happen.
          </DialogDescription>
        </DialogHeader>

        {postmortemId ? (
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Status:</span>
              {statusQuery.data ? (
                <StatusPill
                  status={statusQuery.data.status}
                  tone={STATUS_TONE[statusQuery.data.status]}
                />
              ) : (
                <StatusPill status="pending" tone="muted" />
              )}
            </div>
            {statusQuery.data?.status === "failed" ? (
              <p className="text-sm text-destructive">
                {statusQuery.data.failure_reason ?? "Ingestion failed."}
              </p>
            ) : null}
            {statusQuery.data?.status === "indexed" ? (
              <p className="text-sm text-success">Indexed. It now appears in the table.</p>
            ) : null}
            <div className="flex justify-end">
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Close
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="pm-title">Title</Label>
              <Input
                id="pm-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Checkout outage — connection pool exhaustion"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="pm-raw-text">Document</Label>
              <textarea
                id="pm-raw-text"
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                rows={10}
                placeholder="Summary:&#10;..."
                className="w-full resize-none rounded-md border border-input bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            {errorMessage ? <p className="text-sm text-destructive">{errorMessage}</p> : null}
            <div className="flex justify-end">
              <Button
                onClick={() => void submit()}
                disabled={submitting || !title.trim() || !rawText.trim()}
              >
                {submitting ? "Submitting…" : "Ingest"}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
