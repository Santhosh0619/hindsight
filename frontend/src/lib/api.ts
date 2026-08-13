import type { ApiErrorBody, AuthResponse } from "@/lib/types";

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
