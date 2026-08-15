import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DangerZonePanel } from "@/components/settings/DangerZonePanel";

const mockDeleteWorkspace = vi.fn();
vi.mock("@/lib/api", () => ({
  deleteWorkspace: (...args: unknown[]) => mockDeleteWorkspace(...args),
}));

beforeEach(() => {
  // jsdom doesn't implement real navigation, and `location.assign` isn't
  // configurable enough for vi.spyOn -- replace the whole object instead so the
  // panel's post-delete redirect doesn't throw "Not implemented" inside the test.
  Object.defineProperty(window, "location", {
    value: { ...window.location, assign: vi.fn() },
    writable: true,
  });
});

describe("DangerZonePanel", () => {
  it("keeps the delete button disabled until the typed text matches the workspace name exactly", async () => {
    const user = userEvent.setup();
    render(<DangerZonePanel workspaceId="w1" workspaceName="Acme Corp" />);

    const deleteButton = screen.getByRole("button", { name: "Delete workspace" });
    expect(deleteButton).toBeDisabled();

    await user.type(screen.getByLabelText("Workspace name"), "Acme");
    expect(deleteButton).toBeDisabled();

    await user.clear(screen.getByLabelText("Workspace name"));
    await user.type(screen.getByLabelText("Workspace name"), "Acme Corp");
    expect(deleteButton).toBeEnabled();
  });

  it("calls deleteWorkspace only once the confirmation text matches", async () => {
    mockDeleteWorkspace.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<DangerZonePanel workspaceId="w1" workspaceName="Acme Corp" />);

    await user.type(screen.getByLabelText("Workspace name"), "Acme Corp");
    await user.click(screen.getByRole("button", { name: "Delete workspace" }));

    await waitFor(() => {
      expect(mockDeleteWorkspace).toHaveBeenCalledWith("w1");
    });
  });
});
