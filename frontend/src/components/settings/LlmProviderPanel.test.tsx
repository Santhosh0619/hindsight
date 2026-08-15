import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LlmProviderPanel } from "@/components/settings/LlmProviderPanel";
import type { LLMProviderTestOut } from "@/lib/types";

const mockTestLlmProviders = vi.fn();
vi.mock("@/lib/api", () => ({
  testLlmProviders: (...args: unknown[]) => mockTestLlmProviders(...args),
}));

const RESULTS: LLMProviderTestOut[] = [
  { provider: "gemini", configured: true, ok: true, latency_ms: 240, error: null },
  { provider: "groq", configured: false, ok: null, latency_ms: null, error: null },
  {
    provider: "ollama",
    configured: true,
    ok: false,
    latency_ms: null,
    error: "connection refused",
  },
];

describe("LlmProviderPanel", () => {
  it("shows a prompt before any test has run", () => {
    render(<LlmProviderPanel workspaceId="w1" />);

    expect(
      screen.getByText("Run a connection test to see which providers are reachable.")
    ).toBeInTheDocument();
  });

  it("renders one row per provider after testing, with the right status", async () => {
    mockTestLlmProviders.mockResolvedValue(RESULTS);
    const user = userEvent.setup();
    render(<LlmProviderPanel workspaceId="w1" />);

    await user.click(screen.getByRole("button", { name: "Test connections" }));

    await waitFor(() => {
      expect(screen.getByText("ok · 240ms")).toBeInTheDocument();
    });
    expect(screen.getByText("not configured")).toBeInTheDocument();
    expect(screen.getByText("unreachable")).toBeInTheDocument();
  });

  it("shows an error message when the test call itself fails", async () => {
    mockTestLlmProviders.mockRejectedValue(new Error("network error"));
    const user = userEvent.setup();
    render(<LlmProviderPanel workspaceId="w1" />);

    await user.click(screen.getByRole("button", { name: "Test connections" }));

    await waitFor(() => {
      expect(screen.getByText("network error")).toBeInTheDocument();
    });
  });
});
