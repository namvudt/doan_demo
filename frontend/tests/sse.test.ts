import { describe, expect, it } from "vitest";
import { readEventStream, SseParser } from "../src/api/sse";

const NOW = "2026-11-15T00:00:00.000Z";

const event = (sequence: number, name = "answer.delta") => ({
  sequence,
  event: name,
  data: { text: `Di sản Việt Nam 🏛️ ${sequence}` },
  created_at: NOW,
});

const frame = (
  payload: ReturnType<typeof event>,
  options: { id?: string; name?: string } = {},
) =>
  `id: ${options.id ?? payload.sequence}\nevent: ${options.name ?? payload.event}\ndata: ${JSON.stringify(payload)}\n\n`;

const sseResponse = (body: BodyInit) =>
  new Response(body, { headers: { "Content-Type": "text/event-stream" } });

describe("FastAPI SSE contract", () => {
  it("parses comments, multiline data and CRLF split at arbitrary boundaries", () => {
    const frames: unknown[] = [];
    const parser = new SseParser((value) => frames.push(value));
    const source =
      ": heartbeat\r\nid: 7\r\nevent: answer.delta\r\ndata: dòng một\r\ndata: dòng hai\r\n\r\n";
    for (const char of source) parser.push(char);
    parser.push("", true);
    expect(frames).toEqual([
      { id: "7", event: "answer.delta", data: "dòng một\ndòng hai" },
    ]);
  });

  it("discards an unterminated final frame", () => {
    const frames: unknown[] = [];
    const parser = new SseParser((value) => frames.push(value));
    parser.push("id: 1\ndata: incomplete\n", true);
    expect(frames).toEqual([]);
  });

  it("preserves split UTF-8, ignores cursor replays and returns progress", async () => {
    const bytes = new TextEncoder().encode(frame(event(1)) + frame(event(2)));
    const response = sseResponse(
      new ReadableStream<Uint8Array>({
        start(controller) {
          for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
          controller.close();
        },
      }),
    );
    const received: ReturnType<typeof event>[] = [];
    const result = await readEventStream(response, {
      signal: new AbortController().signal,
      after: 1,
      onEvent: (value) => received.push(value as ReturnType<typeof event>),
    });

    expect(received).toEqual([event(2)]);
    expect(result).toEqual({ lastSequence: 2, received: 1 });
  });

  it("detects sequence gaps so callers can reconcile event history", async () => {
    await expect(
      readEventStream(sseResponse(frame(event(2))), {
        signal: new AbortController().signal,
        onEvent: () => undefined,
      }),
    ).rejects.toMatchObject({
      status: 409,
      code: "EVENT_SEQUENCE_GAP",
      details: { expected: 1, received: 2 },
    });
  });

  it("rejects mismatched frame names and IDs", async () => {
    await expect(
      readEventStream(sseResponse(frame(event(1), { name: "run.completed" })), {
        signal: new AbortController().signal,
        onEvent: () => undefined,
      }),
    ).rejects.toMatchObject({ code: "INVALID_EVENT" });

    await expect(
      readEventStream(sseResponse(frame(event(1), { id: "99" })), {
        signal: new AbortController().signal,
        onEvent: () => undefined,
      }),
    ).rejects.toMatchObject({ code: "INVALID_EVENT" });
  });

  it("rejects malformed payloads and non-SSE responses", async () => {
    await expect(
      readEventStream(sseResponse("id: 1\nevent: answer.delta\ndata: {}\n\n"), {
        signal: new AbortController().signal,
        onEvent: () => undefined,
      }),
    ).rejects.toMatchObject({ code: "INVALID_EVENT" });
    await expect(
      readEventStream(new Response("ok"), {
        signal: new AbortController().signal,
        onEvent: () => undefined,
      }),
    ).rejects.toMatchObject({ code: "INVALID_STREAM" });
  });

  it("turns the explicit expiry event and caller abort into distinct failures", async () => {
    await expect(
      readEventStream(sseResponse("event: session.expired\ndata: {}\n\n"), {
        signal: new AbortController().signal,
        onEvent: () => undefined,
      }),
    ).rejects.toMatchObject({ status: 401, code: "session_expired" });

    const controller = new AbortController();
    controller.abort();
    await expect(
      readEventStream(sseResponse(frame(event(1))), {
        signal: controller.signal,
        onEvent: () => undefined,
      }),
    ).rejects.toMatchObject({ name: "AbortError" });
  });
});
