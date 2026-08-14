import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { NewPostmortemModal } from "@/components/knowledge-base/NewPostmortemModal";

const mockCreatePostmortem = vi.fn();
const mockGetPostmortemStatus = vi.fn();
vi.mock("@/lib/api", () => ({
  createPostmortem: (...args: unknown[]) => mockCreatePostmortem(...args),
  getPostmortemStatus: (...args: unknown[]) => mockGetPostmortemStatus(...args),
}));

function renderModal(onIngested = vi.fn()): { onIngested: () => void } {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <NewPostmortemModal
        workspaceId="w1"
        open={true}
        onOpenChange={vi.fn()}
        onIngested={onIngested}
      />
    </QueryClientProvider>
  );
  return { onIngested };
}

describe("NewPostmortemModal", () => {
  it("submits the form and shows the ingest status once created", async () => {
    mockCreatePostmortem.mockResolvedValue({ id: "pm-1" });
    mockGetPostmortemStatus.mockResolvedValue({
      status: "processing",
      injection_flagged: false,
      failure_reason: null,
    });
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByLabelText("Title"), "Checkout outage");
    await user.type(screen.getByLabelText("Document"), "Summary:\nsomething broke.");
    await user.click(screen.getByRole("button", { name: "Ingest" }));

    expect(mockCreatePostmortem).toHaveBeenCalledWith("w1", {
      title: "Checkout outage",
      raw_text: "Summary:\nsomething broke.",
    });
    await waitFor(() => {
      expect(screen.getByText("processing")).toBeInTheDocument();
    });
  });

  it("calls onIngested once status reaches indexed", async () => {
    mockCreatePostmortem.mockResolvedValue({ id: "pm-1" });
    mockGetPostmortemStatus.mockResolvedValue({
      status: "indexed",
      injection_flagged: false,
      failure_reason: null,
    });
    const user = userEvent.setup();
    const { onIngested } = renderModal();

    await user.type(screen.getByLabelText("Title"), "Checkout outage");
    await user.type(screen.getByLabelText("Document"), "Summary:\nsomething broke.");
    await user.click(screen.getByRole("button", { name: "Ingest" }));

    await waitFor(() => {
      expect(onIngested).toHaveBeenCalled();
    });
    expect(screen.getByText("Indexed. It now appears in the table.")).toBeInTheDocument();
  });

  it("shows the failure reason when ingestion fails", async () => {
    mockCreatePostmortem.mockResolvedValue({ id: "pm-1" });
    mockGetPostmortemStatus.mockResolvedValue({
      status: "failed",
      injection_flagged: false,
      failure_reason: "embedding backend unavailable",
    });
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByLabelText("Title"), "t");
    await user.type(screen.getByLabelText("Document"), "d");
    await user.click(screen.getByRole("button", { name: "Ingest" }));

    await waitFor(() => {
      expect(screen.getByText("embedding backend unavailable")).toBeInTheDocument();
    });
  });

  it("shows an error and stays on the form when creation itself fails", async () => {
    mockCreatePostmortem.mockRejectedValue(new Error("workspace quota exceeded"));
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByLabelText("Title"), "t");
    await user.type(screen.getByLabelText("Document"), "d");
    await user.click(screen.getByRole("button", { name: "Ingest" }));

    await waitFor(() => {
      expect(screen.getByText("workspace quota exceeded")).toBeInTheDocument();
    });
    expect(screen.getByLabelText("Title")).toBeInTheDocument();
  });
});
