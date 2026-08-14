import type { AgentNodeName, AgentStreamEvent } from "@/lib/types";

const NODES: { key: AgentNodeName; label: string }[] = [
  { key: "normalizer", label: "Normalizer" },
  { key: "retriever", label: "Retriever" },
  { key: "correlator", label: "Correlator" },
  { key: "analyst", label: "Analyst" },
  { key: "critic", label: "Critic" },
  { key: "briefer", label: "Briefer" },
];

type NodeState = "queued" | "running" | "done";

const DOWNSTREAM_OF_RETRY: AgentNodeName[] = [
  "retriever",
  "correlator",
  "analyst",
  "critic",
  "briefer",
];

function deriveTrace(events: AgentStreamEvent[]): {
  states: Record<AgentNodeName, NodeState>;
  latencies: Partial<Record<AgentNodeName, number>>;
  retried: boolean;
} {
  const states: Record<AgentNodeName, NodeState> = {
    normalizer: "queued",
    retriever: "queued",
    correlator: "queued",
    analyst: "queued",
    critic: "queued",
    briefer: "queued",
  };
  const latencies: Partial<Record<AgentNodeName, number>> = {};
  let retried = false;

  for (const event of events) {
    if (event.type === "node_start") {
      states[event.node] = "running";
    } else if (event.type === "node_end") {
      states[event.node] = "done";
      latencies[event.node] = event.latency_ms;
    } else if (event.type === "retry") {
      // Control loops back to the retriever -- it and everything downstream resets
      // to queued so the visualization honestly shows the loop, not a stale "done"
      // left over from the first pass.
      retried = true;
      for (const node of DOWNSTREAM_OF_RETRY) {
        states[node] = "queued";
        delete latencies[node];
      }
    }
  }
  return { states, latencies, retried };
}

export function AgentPipelineTrace({ events }: { events: AgentStreamEvent[] }): React.JSX.Element {
  const { states, latencies, retried } = deriveTrace(events);

  return (
    <div className="flex flex-col gap-2">
      {retried ? <p className="text-sm font-medium text-warning">Refining retrieval…</p> : null}
      <div className="flex flex-wrap gap-2">
        {NODES.map(({ key, label }) => {
          const state = states[key];
          const latency = latencies[key];
          return (
            <div
              key={key}
              className={
                "flex items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors " +
                (state === "done"
                  ? "border-success/40 bg-success/10 text-success"
                  : state === "running"
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-border bg-transparent text-muted-foreground")
              }
            >
              <span
                className={
                  "h-2 w-2 rounded-full " +
                  (state === "done"
                    ? "bg-success"
                    : state === "running"
                      ? "animate-pulse bg-accent"
                      : "bg-muted-foreground/40")
                }
              />
              <span className="font-medium">{label}</span>
              {latency !== undefined ? (
                <span className="font-mono text-xs opacity-70">{latency}ms</span>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
