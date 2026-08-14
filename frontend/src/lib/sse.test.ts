import { describe, expect, it, vi } from "vitest";

import { streamSse } from "@/lib/sse";

// sse-starlette's real wire format is CRLF-framed, not the bare LF a naive parser
// might assume (see docs/modules/phase-9-incidents-api/FRD.md Gap #3) -- this fixture
// mirrors the actual bytes `ServerSentEvent.encode()` produces, confirmed live
// against the real library, not guessed.
function crlfSseBody(frames: { event: string; data: string }[]): ReadableStream<Uint8Array> {
  const text = frames.map((f) => `event: ${f.event}\r\ndata: ${f.data}\r\n\r\n`).join("");
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream({
    start(controller) {
      controller.enqueue(bytes);
      controller.close();
    },
  });
}

describe("streamSse", () => {
  it("parses CRLF-framed events exactly like sse-starlette actually sends them", async () => {
    const body = crlfSseBody([
      { event: "node_start", data: '{"type":"node_start","node":"normalizer"}' },
      { event: "node_end", data: '{"type":"node_end","node":"normalizer","latency_ms":12}' },
      { event: "done", data: '{"type":"done","brief_id":"abc-123"}' },
    ]);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 200 })));

    const frames: { event: string; data: string }[] = [];
    await streamSse("http://test/stream", {}, (frame) => frames.push(frame));

    expect(frames).toHaveLength(3);
    expect(frames[0]).toEqual({
      event: "node_start",
      data: '{"type":"node_start","node":"normalizer"}',
    });
    expect(frames[2]).toEqual({ event: "done", data: '{"type":"done","brief_id":"abc-123"}' });

    vi.unstubAllGlobals();
  });

  it("parses events split across multiple chunk boundaries mid-frame", async () => {
    const full = 'event: done\r\ndata: {"type":"done","brief_id":"xyz"}\r\n\r\n';
    const splitAt = 15; // lands inside the "event:" line, not on a frame boundary
    const first = new TextEncoder().encode(full.slice(0, splitAt));
    const second = new TextEncoder().encode(full.slice(splitAt));
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(first);
        controller.enqueue(second);
        controller.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 200 })));

    const frames: { event: string; data: string }[] = [];
    await streamSse("http://test/stream", {}, (frame) => frames.push(frame));

    expect(frames).toEqual([{ event: "done", data: '{"type":"done","brief_id":"xyz"}' }]);

    vi.unstubAllGlobals();
  });

  it("throws when the response is not ok", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 500 })));

    await expect(streamSse("http://test/stream", {}, () => {})).rejects.toThrow("500");

    vi.unstubAllGlobals();
  });
});
