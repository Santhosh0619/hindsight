// Native browser EventSource can't send an Authorization header, and this app has no
// cookie-based API auth to fall back on (see docs/modules/phase-9-incidents-api/FRD.md
// Gap #3) -- so SSE is consumed via fetch() + a hand-rolled frame reader instead,
// exactly like every other API call this app already makes.

export interface SseFrame {
  event: string;
  data: string;
}

export async function streamSse(
  url: string,
  init: RequestInit,
  onFrame: (frame: SseFrame) => void,
  signal?: AbortSignal
): Promise<void> {
  const response = await fetch(url, { ...init, signal });
  if (!response.ok || !response.body) {
    throw new Error(`SSE request failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  // eslint-disable-next-line no-constant-condition -- reader.read() breaks the loop
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    // sse-starlette encodes events with CRLF ("event: x\r\ndata: y\r\n\r\n"), not the
    // bare LF this parser was written against -- "\r\n\r\n" doesn't contain "\n\n" as
    // a substring, so splitting on "\n\n" alone silently never found a frame boundary
    // and every event just accumulated in the buffer forever. Normalizing to LF here
    // keeps the rest of this function's line-based parsing simple and correct for
    // both line-ending styles a server might send.
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const rawFrame of frames) {
      if (!rawFrame.trim()) continue;
      let eventName = "message";
      const dataLines: string[] = [];
      for (const line of rawFrame.split("\n")) {
        if (line.startsWith("event:")) {
          eventName = line.slice("event:".length).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice("data:".length).trim());
        }
      }
      if (dataLines.length > 0) {
        onFrame({ event: eventName, data: dataLines.join("\n") });
      }
    }
  }
}
