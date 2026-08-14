import { streamSse } from "@/lib/sse";
import type {
  AgentStreamEvent,
  ApiErrorBody,
  AuthResponse,
  BlastRadiusOut,
  BriefFeedbackCreate,
  BriefFeedbackOut,
  BriefOut,
  CatalogGraphOut,
  CursorPage,
  DashboardOut,
  IncidentCreate,
  IncidentOut,
  IncidentStatus,
  IncidentUpdate,
  PostmortemCreate,
  PostmortemDetailOut,
  PostmortemOut,
  PostmortemStatus,
  SearchMode,
  SearchResponseOut,
  ServiceOut,
  TeamOut,
} from "@/lib/types";

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  code: string;
  detail: unknown;

  constructor(status: number, code: string, message: string, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

// The access token lives here, in memory only — never localStorage, never a
// non-httpOnly cookie (see NFR "Security"). lib/auth.tsx is the only code that should
// call setAccessToken; everything else just rides along via apiFetch.
let accessToken: string | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

// Endpoints whose own 401 is a real auth failure, not a "session expired" signal —
// retrying these through the refresh flow would either loop forever (/auth/refresh
// itself) or paper over a genuinely wrong password (/auth/login).
const NO_REFRESH_RETRY_PATHS = new Set(["/api/v1/auth/refresh", "/api/v1/auth/login"]);

// Concurrent 401s from simultaneously in-flight requests must trigger exactly one
// /auth/refresh call, not one per request (FR-05) — every caller awaits this same
// in-flight promise instead of starting its own.
let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = (async () => {
    const response = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });

    if (!response.ok) {
      setAccessToken(null);
      throw new ApiError(response.status, "unauthorized", "Session expired", null);
    }

    const body = (await response.json()) as AuthResponse;
    setAccessToken(body.access_token);
    return body.access_token;
  })();

  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
}

async function parseErrorBody(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as ApiErrorBody;
    return new ApiError(response.status, body.error.code, body.error.message, body.error.detail);
  } catch {
    return new ApiError(response.status, "unknown_error", response.statusText, null);
  }
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { body, headers, ...rest } = options;

  const doFetch = async (): Promise<Response> =>
    fetch(`${API_BASE_URL}${path}`, {
      ...rest,
      credentials: "include",
      headers: {
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

  let response = await doFetch();

  if (response.status === 401 && !NO_REFRESH_RETRY_PATHS.has(path)) {
    try {
      await refreshAccessToken();
      response = await doFetch();
    } catch {
      throw await parseErrorBody(response);
    }
  }

  if (!response.ok) {
    throw await parseErrorBody(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

// Query-string construction lives here, not inline at each call site, since search
// has more params than a typical GET this app has made so far (q, mode, limit).
export async function search(
  workspaceId: string,
  params: { q: string; mode: SearchMode; limit?: number }
): Promise<SearchResponseOut> {
  const query = new URLSearchParams({ q: params.q, mode: params.mode });
  if (params.limit !== undefined) {
    query.set("limit", String(params.limit));
  }
  return apiFetch<SearchResponseOut>(
    `/api/v1/workspaces/${workspaceId}/search?${query.toString()}`
  );
}

export async function listServices(workspaceId: string): Promise<ServiceOut[]> {
  return apiFetch<ServiceOut[]>(`/api/v1/workspaces/${workspaceId}/catalog/services`);
}

export async function listTeams(workspaceId: string): Promise<TeamOut[]> {
  return apiFetch<TeamOut[]>(`/api/v1/workspaces/${workspaceId}/catalog/teams`);
}

export async function getGraph(workspaceId: string): Promise<CatalogGraphOut> {
  return apiFetch<CatalogGraphOut>(`/api/v1/workspaces/${workspaceId}/catalog/graph`);
}

export async function getBlastRadius(
  workspaceId: string,
  serviceId: string
): Promise<BlastRadiusOut> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/catalog/services/${serviceId}/blast-radius`);
}

export async function createPostmortem(
  workspaceId: string,
  payload: PostmortemCreate
): Promise<PostmortemOut> {
  return apiFetch<PostmortemOut>(`/api/v1/workspaces/${workspaceId}/postmortems`, {
    method: "POST",
    body: payload,
  });
}

export interface ListPostmortemsParams {
  status?: PostmortemStatus;
  cursor?: string;
  limit?: number;
}

export async function listPostmortems(
  workspaceId: string,
  params: ListPostmortemsParams = {}
): Promise<CursorPage<PostmortemOut>> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch(`/api/v1/workspaces/${workspaceId}/postmortems${suffix}`);
}

export async function getPostmortem(
  workspaceId: string,
  postmortemId: string
): Promise<PostmortemDetailOut> {
  return apiFetch<PostmortemDetailOut>(
    `/api/v1/workspaces/${workspaceId}/postmortems/${postmortemId}`
  );
}

export async function getPostmortemStatus(
  workspaceId: string,
  postmortemId: string
): Promise<{
  status: PostmortemStatus;
  injection_flagged: boolean;
  failure_reason: string | null;
}> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/postmortems/${postmortemId}/status`);
}

export async function getDashboard(workspaceId: string): Promise<DashboardOut> {
  return apiFetch<DashboardOut>(`/api/v1/workspaces/${workspaceId}/dashboard`);
}

export async function createIncident(
  workspaceId: string,
  payload: IncidentCreate
): Promise<IncidentOut> {
  return apiFetch<IncidentOut>(`/api/v1/workspaces/${workspaceId}/incidents`, {
    method: "POST",
    body: payload,
  });
}

export interface ListIncidentsParams {
  status?: IncidentStatus;
  severity?: string;
  service_id?: string;
  cursor?: string;
  limit?: number;
}

export async function listIncidents(
  workspaceId: string,
  params: ListIncidentsParams = {}
): Promise<{ items: IncidentOut[]; next_cursor: string | null }> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch(`/api/v1/workspaces/${workspaceId}/incidents${suffix}`);
}

export async function getIncident(workspaceId: string, incidentId: string): Promise<IncidentOut> {
  return apiFetch<IncidentOut>(`/api/v1/workspaces/${workspaceId}/incidents/${incidentId}`);
}

export async function updateIncident(
  workspaceId: string,
  incidentId: string,
  payload: IncidentUpdate
): Promise<IncidentOut> {
  return apiFetch<IncidentOut>(`/api/v1/workspaces/${workspaceId}/incidents/${incidentId}`, {
    method: "PATCH",
    body: payload,
  });
}

export async function generateBrief(workspaceId: string, incidentId: string): Promise<BriefOut> {
  return apiFetch<BriefOut>(`/api/v1/workspaces/${workspaceId}/incidents/${incidentId}/brief`, {
    method: "POST",
  });
}

export async function listBriefs(workspaceId: string, incidentId: string): Promise<BriefOut[]> {
  return apiFetch<BriefOut[]>(`/api/v1/workspaces/${workspaceId}/incidents/${incidentId}/briefs`);
}

export async function submitFeedback(
  workspaceId: string,
  incidentId: string,
  briefId: string,
  payload: BriefFeedbackCreate
): Promise<BriefFeedbackOut> {
  return apiFetch<BriefFeedbackOut>(
    `/api/v1/workspaces/${workspaceId}/incidents/${incidentId}/brief/${briefId}/feedback`,
    { method: "POST", body: payload }
  );
}

// Drives F5/F6's live pipeline visualization from the real SSE stream (never a
// timer-faked animation, per the FRD). Returns an abort function the caller can use
// to cancel the stream (e.g. on unmount).
export function streamBrief(
  workspaceId: string,
  incidentId: string,
  onEvent: (event: AgentStreamEvent) => void,
  onError: (error: Error) => void
): () => void {
  const controller = new AbortController();

  void streamSse(
    `${API_BASE_URL}/api/v1/workspaces/${workspaceId}/incidents/${incidentId}/brief/stream`,
    {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    },
    (frame) => {
      try {
        onEvent(JSON.parse(frame.data) as AgentStreamEvent);
      } catch {
        // A malformed frame is a protocol bug, not a user-facing error -- drop it
        // rather than tearing down an otherwise-healthy stream over one bad frame.
      }
    },
    controller.signal
  ).catch((error: unknown) => {
    if (controller.signal.aborted) return;
    onError(error instanceof Error ? error : new Error(String(error)));
  });

  return () => controller.abort();
}
