import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/lib/auth";
import { setAccessToken } from "@/lib/api";
import { Login } from "@/pages/Login";

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

function renderLogin(mockFetch: ReturnType<typeof vi.fn>): void {
  vi.stubGlobal("fetch", mockFetch);
  render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <Login />
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("Login", () => {
  it("shows the backend's error message on invalid credentials", async () => {
    const user = userEvent.setup();
    const mockFetch = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/auth/refresh")) {
        return jsonResponse(401, {
          error: { code: "unauthorized", message: "no cookie", detail: null },
        });
      }
      if (url.includes("/auth/login")) {
        return jsonResponse(401, {
          error: { code: "unauthorized", message: "Invalid email or password", detail: null },
        });
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    renderLogin(mockFetch);

    await user.type(screen.getByLabelText("Email"), "a@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Log in" }));

    await waitFor(() => expect(screen.getByText("Invalid email or password")).toBeInTheDocument());
  });

  it("requires both email and password before submitting", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue(
        jsonResponse(401, { error: { code: "unauthorized", message: "no cookie", detail: null } })
      );
    renderLogin(mockFetch);

    // findBy (not getBy) waits for AuthProvider's boot-time refresh to settle first,
    // so its async state update doesn't land after this test's assertions run.
    const emailInput = (await screen.findByLabelText("Email")) as HTMLInputElement;
    const passwordInput = (await screen.findByLabelText("Password")) as HTMLInputElement;

    expect(emailInput).toBeRequired();
    expect(passwordInput).toBeRequired();
  });
});
