// Hand-kept in sync with backend/app/schemas/{auth,workspace,postmortem,search}.py —
// no codegen in this phase (see docs/modules/phase-3-frontend-foundation/NFR.md
// "Constraints").

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

export type Severity = "sev1" | "sev2" | "sev3" | "sev4";
export type PostmortemStatus = "pending" | "processing" | "indexed" | "failed";
export type ServiceLinkRole = "root_cause" | "affected" | "downstream";

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
