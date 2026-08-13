import * as React from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { apiFetch, ApiError, setAccessToken } from "@/lib/api";
import type { AuthResponse, MeResponse, MembershipOut, UserOut, WorkspaceRole } from "@/lib/types";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  user: UserOut | null;
  memberships: MembershipOut[];
  currentMembership: MembershipOut | null;
  status: AuthStatus;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, fullName: string) => Promise<void>;
  loginAsDemo: () => Promise<void>;
  logout: () => Promise<void>;
  setCurrentWorkspace: (workspaceId: string) => void;
}

const AuthContext = React.createContext<AuthContextValue | undefined>(undefined);

interface AuthState {
  user: UserOut | null;
  memberships: MembershipOut[];
  status: AuthStatus;
  currentWorkspaceId: string | null;
}

export function AuthProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [state, setState] = React.useState<AuthState>({
    user: null,
    memberships: [],
    status: "loading",
    currentWorkspaceId: null,
  });

  const applyAuthenticated = React.useCallback(async () => {
    const me = await apiFetch<MeResponse>("/api/v1/auth/me");
    setState((prev) => ({
      user: me.user,
      memberships: me.memberships,
      status: "authenticated",
      currentWorkspaceId: prev.currentWorkspaceId ?? me.memberships[0]?.workspace_id ?? null,
    }));
  }, []);

  const clearSession = React.useCallback(() => {
    setAccessToken(null);
    setState({ user: null, memberships: [], status: "unauthenticated", currentWorkspaceId: null });
  }, []);

  // React 18 StrictMode double-invokes effects in development, which would otherwise
  // fire two near-simultaneous /auth/refresh calls on every mount. Since refresh
  // tokens are single-use with whole-family reuse detection (Phase 2), the second of
  // those two calls sees the first's rotation as a replay and revokes the session
  // that was just legitimately established — a real race, not just StrictMode noise
  // (two browser tabs reloading close together would hit the same race in
  // production). This ref ensures the boot-time refresh actually runs once per app
  // lifetime regardless of how many times the effect callback itself fires.
  const hasBootstrapped = React.useRef(false);

  React.useEffect(() => {
    if (hasBootstrapped.current) {
      return;
    }
    hasBootstrapped.current = true;

    // Silent boot-time refresh: attempts to restore a session from the httpOnly
    // refresh cookie before rendering anything auth-gated (FR-04's "no visible flash").
    (async () => {
      try {
        const resp = await apiFetch<AuthResponse>("/api/v1/auth/refresh", { method: "POST" });
        setAccessToken(resp.access_token);
        await applyAuthenticated();
      } catch {
        clearSession();
      }
    })();
  }, [applyAuthenticated, clearSession]);

  const login = React.useCallback(
    async (email: string, password: string) => {
      const resp = await apiFetch<AuthResponse>("/api/v1/auth/login", {
        method: "POST",
        body: { email, password },
      });
      setAccessToken(resp.access_token);
      await applyAuthenticated();
    },
    [applyAuthenticated]
  );

  const signup = React.useCallback(
    async (email: string, password: string, fullName: string) => {
      const resp = await apiFetch<AuthResponse>("/api/v1/auth/signup", {
        method: "POST",
        body: { email, password, full_name: fullName },
      });
      setAccessToken(resp.access_token);
      await applyAuthenticated();
    },
    [applyAuthenticated]
  );

  const loginAsDemo = React.useCallback(async () => {
    const resp = await apiFetch<AuthResponse>("/api/v1/auth/demo", { method: "POST" });
    setAccessToken(resp.access_token);
    await applyAuthenticated();
  }, [applyAuthenticated]);

  const logout = React.useCallback(async () => {
    try {
      await apiFetch("/api/v1/auth/logout", { method: "POST" });
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const setCurrentWorkspace = React.useCallback((workspaceId: string) => {
    setState((prev) => ({ ...prev, currentWorkspaceId: workspaceId }));
  }, []);

  const currentMembership =
    state.memberships.find((m) => m.workspace_id === state.currentWorkspaceId) ?? null;

  const value: AuthContextValue = {
    user: state.user,
    memberships: state.memberships,
    currentMembership,
    status: state.status,
    login,
    signup,
    loginAsDemo,
    logout,
    setCurrentWorkspace,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// This file mixes component exports (AuthProvider, ProtectedRoute) with hook exports
// (useAuth, useRequireRole) by design — they share AuthContext and splitting them
// into separate files would just add an import hop with no real benefit.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useRequireRole(...roles: WorkspaceRole[]): boolean {
  const { currentMembership } = useAuth();
  return currentMembership !== null && roles.includes(currentMembership.role);
}

export function ProtectedRoute(): React.JSX.Element {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="h-8 w-8 animate-pulse rounded-full bg-muted" />
      </div>
    );
  }

  if (status === "unauthenticated") {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
}

export { ApiError };
