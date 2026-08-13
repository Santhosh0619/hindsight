// Hand-kept in sync with backend/app/schemas/{auth,workspace}.py — no codegen in this
// phase (see docs/modules/phase-3-frontend-foundation/NFR.md "Constraints").

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
