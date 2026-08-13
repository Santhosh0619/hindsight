import { afterEach, describe, expect, it, vi } from "vitest";

import { API_BASE_URL, ApiError, apiFetch, getAccessToken, setAccessToken } from "@/lib/api";

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

describe("apiFetch", () => {
  it("attaches an Authorization header when a token is set", async () => {
    setAccessToken("abc123");
    const mockFetch = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", mockFetch);

    await apiFetch("/api/v1/whatever");

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/api/v1/whatever`,
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer abc123" }),
      })
    );
  });

  it("retries once after a 401 by refreshing the token first", async () => {
    setAccessToken("expired");
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(401, { error: { code: "unauthorized", message: "x", detail: null } })
      )
      .mockResolvedValueOnce(
        jsonResponse(200, { access_token: "fresh", token_type: "bearer", user: {} })
      )
      .mockResolvedValueOnce(jsonResponse(200, { data: "ok" }));
    vi.stubGlobal("fetch", mockFetch);

    const result = await apiFetch("/api/v1/protected");

    expect(result).toEqual({ data: "ok" });
    expect(mockFetch).toHaveBeenCalledTimes(3);
    expect(getAccessToken()).toBe("fresh");
  });

  it("de-dupes concurrent 401s into exactly one refresh call", async () => {
    setAccessToken("expired");
    const callCounts: Record<string, number> = {};

    const mockFetch = vi.fn().mockImplementation(async (url: string) => {
      const path = url.replace(API_BASE_URL, "");
      callCounts[path] = (callCounts[path] ?? 0) + 1;

      if (path === "/api/v1/auth/refresh") {
        return jsonResponse(200, { access_token: "fresh", token_type: "bearer", user: {} });
      }
      if (callCounts[path] === 1) {
        return jsonResponse(401, {
          error: { code: "unauthorized", message: "expired", detail: null },
        });
      }
      return jsonResponse(200, { ok: true });
    });
    vi.stubGlobal("fetch", mockFetch);

    const [a, b] = await Promise.all([apiFetch("/api/v1/a"), apiFetch("/api/v1/b")]);

    expect(a).toEqual({ ok: true });
    expect(b).toEqual({ ok: true });
    expect(callCounts["/api/v1/auth/refresh"]).toBe(1);
  });

  it("does not attempt a refresh when /auth/login itself returns 401", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      jsonResponse(401, {
        error: { code: "unauthorized", message: "Invalid email or password", detail: null },
      })
    );
    vi.stubGlobal("fetch", mockFetch);

    await expect(
      apiFetch("/api/v1/auth/login", { method: "POST", body: { email: "a", password: "b" } })
    ).rejects.toMatchObject({ message: "Invalid email or password" });
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("throws a typed ApiError parsed from the backend's error envelope", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue(
        jsonResponse(409, { error: { code: "conflict", message: "Already exists", detail: null } })
      );
    vi.stubGlobal("fetch", mockFetch);

    await expect(apiFetch("/api/v1/workspaces", { method: "POST", body: {} })).rejects.toThrow(
      ApiError
    );
  });
});
