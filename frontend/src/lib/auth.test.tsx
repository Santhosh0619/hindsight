import * as React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, ProtectedRoute, useAuth, useCanGenerateBrief } from "@/lib/auth";
import { setAccessToken } from "@/lib/api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  setAccessToken(null);
  vi.unstubAllGlobals();
});

function StatusProbe(): React.JSX.Element {
  const { status, user } = useAuth();
  return <div data-testid="status">{`${status}:${user?.email ?? "none"}`}</div>;
}

describe("AuthProvider", () => {
  it("resolves to unauthenticated when the boot-time refresh fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(401, { error: { code: "unauthorized", message: "no cookie", detail: null } })
        )
    );

    render(
      <AuthProvider>
        <StatusProbe />
      </AuthProvider>
    );

    expect(screen.getByTestId("status")).toHaveTextContent("loading:none");
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated:none")
    );
  });

  it("resolves to authenticated when the boot-time refresh succeeds", async () => {
    const mockFetch = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/auth/refresh")) {
        return jsonResponse(200, {
          access_token: "tok",
          token_type: "bearer",
          user: { id: "1", email: "a@example.com", full_name: "A", is_demo: false },
        });
      }
      if (url.includes("/auth/me")) {
        return jsonResponse(200, {
          user: { id: "1", email: "a@example.com", full_name: "A", is_demo: false },
          memberships: [
            {
              workspace_id: "w1",
              workspace_name: "A's workspace",
              workspace_slug: "a",
              workspace_is_demo: false,
              role: "owner",
            },
          ],
        });
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", mockFetch);

    render(
      <AuthProvider>
        <StatusProbe />
      </AuthProvider>
    );

    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("authenticated:a@example.com")
    );
  });

  it("calls /auth/refresh exactly once even under StrictMode's double-invoked effects", async () => {
    // Regression test for the race documented in
    // docs/decisions/0003-phase-3-frontend-foundation.md #2: StrictMode firing the
    // boot effect twice used to send two concurrent refresh calls, and Phase 2's
    // reuse detection would revoke the whole session as a false-positive replay.
    let refreshCalls = 0;
    const mockFetch = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/auth/refresh")) {
        refreshCalls += 1;
        return jsonResponse(200, {
          access_token: "tok",
          token_type: "bearer",
          user: { id: "1", email: "a@example.com", full_name: "A", is_demo: false },
        });
      }
      if (url.includes("/auth/me")) {
        return jsonResponse(200, {
          user: { id: "1", email: "a@example.com", full_name: "A", is_demo: false },
          memberships: [],
        });
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", mockFetch);

    render(
      <React.StrictMode>
        <AuthProvider>
          <StatusProbe />
        </AuthProvider>
      </React.StrictMode>
    );

    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("authenticated:a@example.com")
    );
    expect(refreshCalls).toBe(1);
  });
});

describe("ProtectedRoute", () => {
  it("redirects to /login when unauthenticated", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(401, { error: { code: "unauthorized", message: "no cookie", detail: null } })
        )
    );

    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<div>Login page</div>} />
            <Route element={<ProtectedRoute />}>
              <Route path="/dashboard" element={<div>Dashboard</div>} />
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText("Login page")).toBeInTheDocument());
  });

  it("renders the protected content when authenticated", async () => {
    const mockFetch = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/auth/refresh")) {
        return jsonResponse(200, {
          access_token: "tok",
          token_type: "bearer",
          user: { id: "1", email: "a@example.com", full_name: "A", is_demo: false },
        });
      }
      if (url.includes("/auth/me")) {
        return jsonResponse(200, {
          user: { id: "1", email: "a@example.com", full_name: "A", is_demo: false },
          memberships: [],
        });
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", mockFetch);

    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/dashboard"]}>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<div>Login page</div>} />
              <Route element={<ProtectedRoute />}>
                <Route path="/dashboard" element={<div>Dashboard</div>} />
              </Route>
            </Routes>
          </AuthProvider>
        </MemoryRouter>
      );
    });

    await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());
  });
});

function CanGenerateBriefProbe(): React.JSX.Element {
  const canGenerateBrief = useCanGenerateBrief();
  const { memberships, setCurrentWorkspace } = useAuth();
  return (
    <div>
      <div data-testid="can-generate">{String(canGenerateBrief)}</div>
      {memberships.map((m) => (
        <button key={m.workspace_id} onClick={() => setCurrentWorkspace(m.workspace_id)}>
          {m.workspace_name}
        </button>
      ))}
    </div>
  );
}

describe("useCanGenerateBrief", () => {
  it("is false for a demo guest viewing a real workspace they've also joined", async () => {
    // Regression test for the frontend/backend mismatch fixed alongside
    // backend/app/core/deps.py's require_role_or_demo scoping: a demo guest's
    // is_demo flag is permanent on the account, so the hook must also check the
    // *currently viewed* workspace's own workspace_is_demo, not just the account.
    const mockFetch = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/auth/refresh")) {
        return jsonResponse(200, {
          access_token: "tok",
          token_type: "bearer",
          user: {
            id: "1",
            email: "guest@demo.hindsight.local",
            full_name: "Demo Guest",
            is_demo: true,
          },
        });
      }
      if (url.includes("/auth/me")) {
        return jsonResponse(200, {
          user: {
            id: "1",
            email: "guest@demo.hindsight.local",
            full_name: "Demo Guest",
            is_demo: true,
          },
          memberships: [
            {
              workspace_id: "demo-ws",
              workspace_name: "Demo Workspace",
              workspace_slug: "demo",
              workspace_is_demo: true,
              role: "viewer",
            },
            {
              workspace_id: "real-ws",
              workspace_name: "Real Workspace",
              workspace_slug: "real",
              workspace_is_demo: false,
              role: "viewer",
            },
          ],
        });
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", mockFetch);

    render(
      <AuthProvider>
        <CanGenerateBriefProbe />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("can-generate")).toHaveTextContent("true"));

    act(() => {
      screen.getByRole("button", { name: "Real Workspace" }).click();
    });

    await waitFor(() => expect(screen.getByTestId("can-generate")).toHaveTextContent("false"));
  });

  it("is true for an owner regardless of any workspace's demo status", async () => {
    const mockFetch = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/auth/refresh")) {
        return jsonResponse(200, {
          access_token: "tok",
          token_type: "bearer",
          user: { id: "2", email: "owner@example.com", full_name: "Owner", is_demo: false },
        });
      }
      if (url.includes("/auth/me")) {
        return jsonResponse(200, {
          user: { id: "2", email: "owner@example.com", full_name: "Owner", is_demo: false },
          memberships: [
            {
              workspace_id: "real-ws",
              workspace_name: "Real Workspace",
              workspace_slug: "real",
              workspace_is_demo: false,
              role: "owner",
            },
          ],
        });
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", mockFetch);

    render(
      <AuthProvider>
        <CanGenerateBriefProbe />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("can-generate")).toHaveTextContent("true"));
  });
});
