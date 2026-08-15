import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MembersPanel } from "@/components/settings/MembersPanel";
import type { MemberOut } from "@/lib/types";

const mockListMembers = vi.fn();
const mockRotateInviteCode = vi.fn();
const mockChangeMemberRole = vi.fn();
const mockRemoveMember = vi.fn();
vi.mock("@/lib/api", () => ({
  listMembers: (...args: unknown[]) => mockListMembers(...args),
  rotateInviteCode: (...args: unknown[]) => mockRotateInviteCode(...args),
  changeMemberRole: (...args: unknown[]) => mockChangeMemberRole(...args),
  removeMember: (...args: unknown[]) => mockRemoveMember(...args),
}));

const MEMBERS: MemberOut[] = [
  {
    user_id: "u1",
    email: "owner@example.com",
    full_name: "Owner Person",
    role: "owner",
    joined_at: "2026-01-01T00:00:00Z",
  },
  {
    user_id: "u2",
    email: "resp@example.com",
    full_name: "Responder Person",
    role: "responder",
    joined_at: "2026-01-02T00:00:00Z",
  },
];

function renderPanel(canManage: boolean): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MembersPanel workspaceId="w1" canManage={canManage} />
    </QueryClientProvider>
  );
}

describe("MembersPanel", () => {
  beforeEach(() => {
    mockListMembers.mockReset();
    mockRotateInviteCode.mockReset();
    mockChangeMemberRole.mockReset();
    mockRemoveMember.mockReset();
    mockListMembers.mockResolvedValue(MEMBERS);
  });

  it("renders every member", async () => {
    renderPanel(true);

    await waitFor(() => {
      expect(screen.getByText("Owner Person")).toBeInTheDocument();
    });
    expect(screen.getByText("Responder Person")).toBeInTheDocument();
  });

  it("shows role-change and remove controls when canManage is true", async () => {
    renderPanel(true);

    await waitFor(() => screen.getByText("Owner Person"));
    expect(screen.getAllByRole("button", { name: "Remove" })).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Rotate invite code" })).toBeInTheDocument();
  });

  it("hides mutation controls and shows a read-only role badge when canManage is false", async () => {
    renderPanel(false);

    await waitFor(() => screen.getByText("Owner Person"));
    expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Rotate invite code" })).not.toBeInTheDocument();
    expect(screen.getByText("owner")).toBeInTheDocument();
  });

  it("removes a member on click", async () => {
    mockRemoveMember.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPanel(true);

    await waitFor(() => screen.getByText("Owner Person"));
    const removeButtons = screen.getAllByRole("button", { name: "Remove" });
    await user.click(removeButtons[1] as HTMLElement);

    await waitFor(() => {
      expect(mockRemoveMember).toHaveBeenCalledWith("w1", "u2");
    });
  });
});
