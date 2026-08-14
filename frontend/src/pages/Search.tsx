import * as React from "react";
import { useQuery } from "@tanstack/react-query";

import { EmptyState } from "@/components/layout/EmptyState";
import { LoadingSkeleton } from "@/components/layout/LoadingSkeleton";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { SeverityBadge } from "@/components/ui/severity-badge";
import { Timestamp } from "@/components/ui/timestamp";
import { search } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { SearchMode, SearchResultOut, SourceName } from "@/lib/types";

const MODES: { value: SearchMode; label: string }[] = [
  { value: "hybrid", label: "Hybrid" },
  { value: "vector", label: "Vector" },
  { value: "keyword", label: "Keyword" },
  { value: "graph", label: "Graph" },
];

const SOURCE_VARIANT: Record<SourceName, "default" | "success" | "warning"> = {
  vector: "default",
  keyword: "success",
  graph: "warning",
};

const DEBOUNCE_MS = 300;

function useDebouncedValue(value: string, delayMs: number): string {
  const [debounced, setDebounced] = React.useState(value);
  React.useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

function ResultCard({ result }: { result: SearchResultOut }): React.JSX.Element {
  const { postmortem } = result;
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
        <div>
          <CardTitle className="text-base">{postmortem.title}</CardTitle>
          <div className="mt-1 flex items-center gap-2">
            {postmortem.severity ? <SeverityBadge severity={postmortem.severity} /> : null}
            <Timestamp value={postmortem.occurred_at ?? postmortem.created_at} />
          </div>
        </div>
        <div className="flex flex-wrap justify-end gap-1.5">
          {result.sources.map((source) => (
            <Badge key={source.source} variant={SOURCE_VARIANT[source.source]}>
              {source.source} #{source.rank}
            </Badge>
          ))}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {result.chunk_excerpt ? (
          <p className="text-sm text-muted-foreground">
            {result.chunk_excerpt.section_label ? (
              <span className="font-medium text-foreground">
                {result.chunk_excerpt.section_label}:{" "}
              </span>
            ) : null}
            {result.chunk_excerpt.content}
          </p>
        ) : null}
        {result.graph_reason ? (
          <p className="text-sm text-muted-foreground">
            via {result.graph_reason.matched_service_name}
            {result.graph_reason.via_service_name
              ? `'s neighbor ${result.graph_reason.via_service_name}`
              : ""}{" "}
            ({result.graph_reason.role.replace("_", " ")})
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function Search(): React.JSX.Element {
  const { currentMembership } = useAuth();
  const currentWorkspaceId = currentMembership?.workspace_id ?? null;
  const [queryInput, setQueryInput] = React.useState("");
  const [mode, setMode] = React.useState<SearchMode>("hybrid");
  const debouncedQuery = useDebouncedValue(queryInput, DEBOUNCE_MS);
  const trimmedQuery = debouncedQuery.trim();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["search", currentWorkspaceId, mode, trimmedQuery],
    queryFn: () => search(currentWorkspaceId as string, { q: trimmedQuery, mode }),
    enabled: Boolean(currentWorkspaceId) && trimmedQuery.length > 0,
  });

  return (
    <>
      <PageHeader
        title="Search"
        description="Hybrid search across every postmortem — vector, keyword, and graph, fused."
      />
      <div className="flex flex-col gap-4">
        <Input
          value={queryInput}
          onChange={(e) => setQueryInput(e.target.value)}
          placeholder="Search postmortems, error codes, service names…"
          aria-label="Search query"
        />
        <div className="flex gap-1.5" role="tablist" aria-label="Search mode">
          {MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              role="tab"
              aria-selected={mode === m.value}
              onClick={() => setMode(m.value)}
              className={
                "rounded-md border px-3 py-1.5 text-sm font-medium transition-colors " +
                (mode === m.value
                  ? "border-accent bg-accent text-accent-foreground"
                  : "border-border bg-transparent text-muted-foreground hover:bg-muted")
              }
            >
              {m.label}
            </button>
          ))}
        </div>

        {trimmedQuery.length === 0 ? (
          <EmptyState
            title="Search your knowledge base"
            description="Try an error code, a service name, or a description of what went wrong."
          />
        ) : isLoading ? (
          <LoadingSkeleton lines={5} />
        ) : isError ? (
          <EmptyState
            title="Search failed"
            description="Something went wrong running that search. Try again."
          />
        ) : data && data.results.length === 0 ? (
          <EmptyState
            title="No results"
            description={`Nothing matched "${trimmedQuery}" in ${mode} mode.`}
          />
        ) : (
          <div className="flex flex-col gap-3">
            {data?.results.map((result) => (
              <ResultCard key={result.postmortem.id} result={result} />
            ))}
          </div>
        )}
      </div>
    </>
  );
}
