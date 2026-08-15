import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiKeysPanel } from "@/components/settings/ApiKeysPanel";
import type { ApiKeyOut } from "@/lib/types";

const mockListApiKeys = vi.fn();
const mockCreateApiKey = vi.fn();
const mockRevokeApiKey = vi.fn();
vi.mock("@/lib/api", () => ({
  listApiKeys: (...args: unknown[]) => mockListApiKeys(...args),
  createApiKey: (...args: unknown[]) => mockCreateApiKey(...args),
  revokeApiKey: (...args: unknown[]) => mockRevokeApiKey(...args),
}));

const KEYS: ApiKeyOut[] = [
  {
    id: "key-1",
    name: "pagerduty webhook",
    prefix: "hs_abc123defg",
    created_by: "u1",
    created_at: "2026-01-01T00:00:00Z",
    last_used_at: null,
    revoked_at: null,
  },
];

function renderPanel(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ApiKeysPanel workspaceId="w1" />
    </QueryClientProvider>
  );
}

describe("ApiKeysPanel", () => {
  beforeEach(() => {
    mockListApiKeys.mockReset();
    mockCreateApiKey.mockReset();
    mockRevokeApiKey.mockReset();
    mockListApiKeys.mockResolvedValue(KEYS);
  });

  it("renders existing keys by name and prefix, never the raw key", async () => {
    renderPanel();

    await waitFor(() => {
      expect(screen.getByText("pagerduty webhook")).toBeInTheDocument();
    });
    expect(screen.getByText("hs_abc123defg…")).toBeInTheDocument();
  });

  it("shows the raw key exactly once after creation, then hides it on dismiss", async () => {
    mockCreateApiKey.mockResolvedValue({
      id: "key-2",
      name: "new key",
      prefix: "hs_xyz",
      raw_key: "hs_xyzSECRETVALUE",
      created_at: "2026-08-15T00:00:00Z",
    });
    const user = userEvent.setup();
    renderPanel();

    await waitFor(() => screen.getByText("pagerduty webhook"));
    await user.type(screen.getByLabelText("New API key name"), "new key");
    await user.click(screen.getByRole("button", { name: "Create key" }));

    await waitFor(() => {
      expect(screen.getByText("hs_xyzSECRETVALUE")).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "Done, I've copied it" }));
    expect(screen.queryByText("hs_xyzSECRETVALUE")).not.toBeInTheDocument();
  });

  it("revokes a key on click", async () => {
    mockRevokeApiKey.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPanel();

    await waitFor(() => screen.getByText("pagerduty webhook"));
    await user.click(screen.getByRole("button", { name: "Revoke" }));

    await waitFor(() => {
      expect(mockRevokeApiKey).toHaveBeenCalledWith("w1", "key-1");
    });
  });

  it("shows a revoked marker instead of the revoke button for a revoked key", async () => {
    mockListApiKeys.mockResolvedValue([{ ...KEYS[0], revoked_at: "2026-08-14T00:00:00Z" }]);
    renderPanel();

    await waitFor(() => {
      expect(screen.getByText("revoked")).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: "Revoke" })).not.toBeInTheDocument();
  });
});
