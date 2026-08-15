import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuditLog } from "@/pages/AuditLog";
import type { AuditLogEntryOut, MemberOut } from "@/lib/types";

const mockUseAuth = vi.fn();
vi.mock("@/lib/auth", () => ({
  useAuth: () => mockUseAuth(),
}));

const mockGetAuditLog = vi.fn();
const mockListMembers = vi.fn();
vi.mock("@/lib/api", () => ({
  getAuditLog: (...args: unknown[]) => mockGetAuditLog(...args),
  listMembers: (...args: unknown[]) => mockListMembers(...args),
}));

mockUseAuth.mockReturnValue({
  currentMembership: {
    workspace_id: "w1",
    workspace_name: "W",
    workspace_slug: "w",
    role: "owner",
  },
});

const ENTRY: AuditLogEntryOut = {
  id: "log-1",
  actor_user_id: "u1",
  action: "api_key.created",
  target_type: "api_key",
  target_id: "key-1",
  meta: {},
  created_at: "2026-08-15T00:00:00Z",
};

const MEMBERS: MemberOut[] = [
  {
    user_id: "u1",
    email: "owner@example.com",
    full_name: "Owner Person",
    role: "owner",
    joined_at: "2026-01-01T00:00:00Z",
  },
];

function renderPage(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AuditLog />
    </QueryClientProvider>
  );
}

describe("AuditLog", () => {
  beforeEach(() => {
    mockGetAuditLog.mockReset();
    mockListMembers.mockReset();
    mockListMembers.mockResolvedValue(MEMBERS);
  });

  it("renders audit log entries", async () => {
    mockGetAuditLog.mockResolvedValue({ items: [ENTRY], next_cursor: null });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("api_key.created")).toBeInTheDocument();
    });
    expect(screen.getByText(/api_key · key-1/)).toBeInTheDocument();
  });

  it("shows an empty state when there are no matching entries", async () => {
    mockGetAuditLog.mockResolvedValue({ items: [], next_cursor: null });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("No matching entries")).toBeInTheDocument();
    });
  });

  it("shows an error state when the audit log fails to load", async () => {
    mockGetAuditLog.mockRejectedValue(new Error("boom"));
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Couldn't load the audit log")).toBeInTheDocument();
    });
  });
});
