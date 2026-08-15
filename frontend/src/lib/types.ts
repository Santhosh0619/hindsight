// Hand-kept in sync with backend/app/schemas/{auth,workspace,postmortem,search,
// catalog,incident_api}.py — no codegen in this phase (see
// docs/modules/phase-3-frontend-foundation/NFR.md "Constraints").

export type WorkspaceRole = "owner" | "responder" | "viewer";

export interface UserOut {
  id: string;
  email: string;
  full_name: string;
  is_demo: boolean;
}

export interface MembershipOut {
  workspace_id: string;
  workspace_name: string;
  workspace_slug: string;
  workspace_is_demo: boolean;
  role: WorkspaceRole;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: UserOut;
}

export interface MeResponse {
  user: UserOut;
  memberships: MembershipOut[];
}

export interface WorkspaceOut {
  id: string;
  name: string;
  slug: string;
  is_demo: boolean;
  created_at: string;
  role: WorkspaceRole;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    detail: unknown;
  };
}

export interface CursorPage<T> {
  items: T[];
  next_cursor: string | null;
}

export type Severity = "sev1" | "sev2" | "sev3" | "sev4";
export type PostmortemStatus = "pending" | "processing" | "indexed" | "failed";
export type ServiceLinkRole = "root_cause" | "affected" | "downstream";

export interface PostmortemCreate {
  title: string;
  raw_text: string;
  external_ref?: string;
  occurred_at?: string;
  duration_minutes?: number;
  severity?: Severity;
}

export interface PostmortemServiceLinkOut {
  service: ServiceOut;
  role: ServiceLinkRole;
  confidence: number | null;
}

export interface PostmortemOut {
  id: string;
  external_ref: string | null;
  title: string;
  occurred_at: string | null;
  duration_minutes: number | null;
  severity: Severity | null;
  status: PostmortemStatus;
  injection_flagged: boolean;
  failure_reason: string | null;
  created_at: string;
  affected_services: PostmortemServiceLinkOut[];
}

export type FactType =
  "trigger" | "root_cause" | "remediation" | "detection_gap" | "contributing_factor";

export interface PostmortemFactOut {
  fact_type: FactType;
  statement: string;
  confidence: number | null;
  source_chunk_id: string;
  char_start: number;
  char_end: number;
}

export interface PostmortemChunkOut {
  id: string;
  chunk_index: number;
  section_label: string | null;
  content: string;
  char_start: number;
  char_end: number;
}

export interface PostmortemDetailOut extends PostmortemOut {
  chunks: PostmortemChunkOut[];
  redacted_text: string | null;
  facts: PostmortemFactOut[];
}

export type SearchMode = "hybrid" | "vector" | "keyword" | "graph";
export type SourceName = "vector" | "keyword" | "graph";

export interface SourceHitOut {
  source: SourceName;
  rank: number;
  raw_score: number;
}

export interface ChunkExcerptOut {
  chunk_id: string;
  section_label: string | null;
  content: string;
}

export interface GraphReasonOut {
  matched_service_name: string;
  via_service_name: string | null;
  role: ServiceLinkRole;
}

export interface SearchResultOut {
  postmortem: PostmortemOut;
  score: number;
  sources: SourceHitOut[];
  chunk_excerpt: ChunkExcerptOut | null;
  graph_reason: GraphReasonOut | null;
}

export interface SearchResponseOut {
  results: SearchResultOut[];
  mode: SearchMode;
  timings_ms: Record<string, number>;
}

// --- Catalog (Phase 4, first frontend consumer this phase) ---

export type ServiceTier = 1 | 2 | 3;

export interface ServiceOut {
  id: string;
  name: string;
  tier: ServiceTier;
  team_id: string | null;
  repo_url: string | null;
  description: string | null;
  runbook_url: string | null;
}

export interface BlastRadiusEntryOut {
  service: ServiceOut;
  score: number;
  path: ServiceOut[];
  depth: number;
}

export interface BlastRadiusOut {
  services: BlastRadiusEntryOut[];
}

export interface TeamOut {
  id: string;
  name: string;
  slack_handle: string | null;
  escalation_contact: string | null;
}

export type EdgeKind = "calls" | "reads_from" | "publishes_to" | "depends_on";
export type EdgeCriticality = "hard" | "soft";

export interface EdgeOut {
  id: string;
  from_service_id: string;
  to_service_id: string;
  kind: EdgeKind;
  criticality: EdgeCriticality;
}

export interface CatalogGraphOut {
  nodes: ServiceOut[];
  edges: EdgeOut[];
}

// --- Incidents (Phase 9) ---

export type IncidentStatus = "open" | "mitigated" | "resolved" | "false_positive";
export type FeedbackVerdict = "helpful" | "partially" | "unhelpful";

export interface IncidentOut {
  id: string;
  workspace_id: string;
  external_ref: string | null;
  title: string;
  raw_alert_text: string;
  severity: Severity | null;
  status: IncidentStatus;
  opened_by: string | null;
  opened_at: string;
  resolved_at: string | null;
  created_at: string;
}

export interface IncidentCreate {
  title: string;
  raw_alert_text: string;
  external_ref?: string;
  severity?: Severity;
}

export interface IncidentUpdate {
  status?: IncidentStatus;
  title?: string;
}

export interface CitationOut {
  chunk_id: string;
  postmortem_id: string;
  postmortem_title: string;
  quote: string | null;
  content: string;
  char_start: number;
  char_end: number;
}

export interface HypothesisOut {
  statement: string;
  confidence: number;
  citations: CitationOut[];
}

export interface RunbookStepOut {
  step: string;
  source_postmortem_id: string | null;
  citation: CitationOut | null;
}

export interface MatchedPostmortemOut {
  postmortem: PostmortemOut;
  vector_score: number;
  keyword_score: number;
  graph_score: number;
  failure_mode_overlap: number;
  recency: number;
  overall_score: number;
  rank: number;
}

export interface BriefOut {
  id: string;
  incident_id: string;
  version: number;
  hypotheses: HypothesisOut[];
  matched_postmortems: MatchedPostmortemOut[];
  blast_radius: BlastRadiusOut;
  runbook_steps: RunbookStepOut[];
  citations: CitationOut[];
  overall_confidence: number | null;
  correction_passes: number;
  llm_used: boolean;
  from_cache: boolean;
  generated_at: string | null;
}

export interface BriefFeedbackCreate {
  verdict: FeedbackVerdict;
  correct_postmortem_id?: string;
  note?: string;
}

export interface BriefFeedbackOut {
  id: string;
  brief_id: string;
  user_id: string | null;
  verdict: FeedbackVerdict;
  correct_postmortem_id: string | null;
  note: string | null;
  created_at: string;
}

// SSE events from GET /incidents/{id}/brief/stream (app/agents/streaming.py's
// stream_graph_events shapes, wrapped by /lib/sse.ts).
export type AgentNodeName =
  "normalizer" | "retriever" | "correlator" | "analyst" | "critic" | "briefer";

export type AgentStreamEvent =
  | { type: "node_start"; node: AgentNodeName }
  | { type: "node_end"; node: AgentNodeName; latency_ms: number }
  | { type: "retry" }
  | { type: "done"; brief_id: string | null }
  | { type: "error"; message: string };

// --- Dashboard (Phase 10) ---

export interface IngestHealthOut {
  indexed: number;
  processing: number;
  pending: number;
  failed: number;
}

export interface MttrPointOut {
  week_start: string;
  mttr_minutes: number | null;
}

export interface FragileServiceOut {
  service: ServiceOut;
  incident_count: number;
  blast_radius_size: number;
  fragility_score: number;
}

export interface RecentBriefOut {
  incident_id: string;
  incident_title: string;
  brief_id: string;
  version: number;
  overall_confidence: number | null;
  generated_at: string | null;
}

export interface DashboardOut {
  open_incidents: number;
  briefs_generated: number;
  corpus_size: number;
  ingest_health: IngestHealthOut;
  mttr_trend: MttrPointOut[];
  fragile_services: FragileServiceOut[];
  recent_briefs: RecentBriefOut[];
}
