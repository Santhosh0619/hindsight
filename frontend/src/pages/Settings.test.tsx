import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Settings } from "@/pages/Settings";

const mockUseAuth = vi.fn();
const mockUseRequireRole = vi.fn();
vi.mock("@/lib/auth", () => ({
  useAuth: () => mockUseAuth(),
  useRequireRole: (...roles: string[]) => mockUseRequireRole(...roles),
}));

const mockListMembers = vi.fn();
vi.mock("@/lib/api", () => ({
  listMembers: (...args: unknown[]) => mockListMembers(...args),
  rotateInviteCode: vi.fn(),
  changeMemberRole: vi.fn(),
  removeMember: vi.fn(),
  updateWorkspace: vi.fn(),
  listApiKeys: vi.fn().mockResolvedValue([]),
  createApiKey: vi.fn(),
  revokeApiKey: vi.fn(),
  testLlmProviders: vi.fn(),
  deleteWorkspace: vi.fn(),
}));

function renderPage(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <Settings />
    </QueryClientProvider>
  );
}

describe("Settings", () => {
  beforeEach(() => {
    mockListMembers.mockReset();
    mockListMembers.mockResolvedValue([]);
    mockUseAuth.mockReturnValue({
      currentMembership: {
        workspace_id: "w1",
        workspace_name: "Acme Corp",
        workspace_slug: "acme",
        role: "owner",
      },
    });
  });

  it("renders API keys, LLM provider, and danger zone panels for an owner", async () => {
    mockUseRequireRole.mockReturnValue(true);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("API keys")).toBeInTheDocument();
    });
    expect(screen.getByText("LLM provider connection")).toBeInTheDocument();
    expect(screen.getByText("Danger zone")).toBeInTheDocument();
    expect(screen.getByText("General")).toBeInTheDocument();
  });

  it("hides owner-only panels and shows a note for a non-owner", async () => {
    mockUseRequireRole.mockReturnValue(false);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Members")).toBeInTheDocument();
    });
    expect(screen.queryByText("API keys")).not.toBeInTheDocument();
    expect(screen.queryByText("Danger zone")).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "API keys, LLM provider connectivity, and workspace administration are managed by an owner."
      )
    ).toBeInTheDocument();
  });

  it("shows an empty state when there is no current workspace", () => {
    mockUseAuth.mockReturnValue({ currentMembership: null });
    mockUseRequireRole.mockReturnValue(false);
    renderPage();

    expect(screen.getByText("No workspace selected")).toBeInTheDocument();
  });
});
