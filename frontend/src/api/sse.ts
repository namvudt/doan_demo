import { ApiError, type StreamReadResult } from "./contracts";
import { eventViewSchema, type EventView } from "./schema";

export type SseFrame = { event: string; data: string; id: string };

/** Incremental WHATWG SSE framing. Chunks may split CRLF and UTF-8 text anywhere. */
export class SseParser {
  private buffer = "";
  private dataLines: string[] = [];
  private eventName = "message";
  private lastEventId = "";

  constructor(private readonly emit: (frame: SseFrame) => void) {}

  push(chunk: string, final = false) {
    this.buffer += chunk;
    let cursor = 0;

    while (cursor < this.buffer.length) {
      const char = this.buffer[cursor];
      if (char !== "\r" && char !== "\n") {
        cursor += 1;
        continue;
      }
      if (char === "\r" && cursor === this.buffer.length - 1 && !final) break;

      const line = this.buffer.slice(0, cursor);
      const lineEndingWidth =
        char === "\r" && this.buffer[cursor + 1] === "\n" ? 2 : 1;
      this.buffer = this.buffer.slice(cursor + lineEndingWidth);
      cursor = 0;
      this.processLine(line);
    }

    // Per the SSE algorithm, EOF without a blank line does not dispatch an event.
    if (final) this.buffer = "";
  }

  private processLine(line: string) {
    if (line === "") {
      if (this.dataLines.length > 0) {
        this.emit({
          event: this.eventName,
          data: this.dataLines.join("\n"),
          id: this.lastEventId,
        });
      }
      this.dataLines = [];
      this.eventName = "message";
      return;
    }

    if (line.startsWith(":")) return;

    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);

    if (field === "data") this.dataLines.push(value);
    else if (field === "event") this.eventName = value;
    else if (field === "id" && !value.includes("\0")) this.lastEventId = value;
    // The server does not currently emit retry; browsers own reconnect policy.
  }
}

export type ReadEventStreamOptions = {
  signal: AbortSignal;
  onEvent: (event: EventView) => void;
  /** Last sequence already applied by the caller. Replayed events are ignored. */
  after?: number;
  /** Detect missing records instead of silently presenting an incomplete run. */
  requireContiguous?: boolean;
};

const abortError = () =>
  new DOMException("The operation was aborted.", "AbortError");

export async function readEventStream(
  response: Response,
  options: ReadEventStreamOptions,
): Promise<StreamReadResult> {
  const { signal, onEvent, requireContiguous = true } = options;
  let lastSequence = options.after ?? 0;
  let received = 0;

  if (signal.aborted) throw abortError();
  if (!response.body) {
    throw new ApiError("Server không trả về luồng sự kiện.", 502, "NO_STREAM");
  }
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (!contentType.includes("text/event-stream")) {
    throw new ApiError(
      "API streaming phải trả Content-Type: text/event-stream.",
      502,
      "INVALID_STREAM",
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser((frame) => {
    if (frame.event === "ping") return;
    if (frame.event === "session.expired") {
      throw new ApiError(
        "Phiên truy cập backend đã hết hạn.",
        401,
        "session_expired",
      );
    }

    let payload: unknown;
    try {
      payload = JSON.parse(frame.data);
    } catch (cause) {
      throw new ApiError(
        "Sự kiện SSE không phải JSON hợp lệ.",
        502,
        "INVALID_EVENT",
        undefined,
        undefined,
        cause,
      );
    }

    const parsed = eventViewSchema.safeParse(payload);
    if (!parsed.success) {
      throw new ApiError(
        "Sự kiện SSE không khớp hợp đồng API.",
        502,
        "INVALID_EVENT",
        parsed.error.flatten(),
      );
    }

    const event = parsed.data;
    if (frame.event !== event.event) {
      throw new ApiError(
        "Tên sự kiện SSE không đồng nhất với payload.",
        502,
        "INVALID_EVENT",
        { frame_event: frame.event, payload_event: event.event },
      );
    }
    if (frame.id !== String(event.sequence)) {
      throw new ApiError(
        "ID của sự kiện SSE không đồng nhất với sequence.",
        502,
        "INVALID_EVENT",
        { frame_id: frame.id, sequence: event.sequence },
      );
    }

    // Reconnects can replay records at or before the cursor.
    if (event.sequence <= lastSequence) return;
    if (requireContiguous && event.sequence !== lastSequence + 1) {
      throw new ApiError(
        "Luồng sự kiện bị thiếu sequence; cần đồng bộ lại bằng event history.",
        409,
        "EVENT_SEQUENCE_GAP",
        { expected: lastSequence + 1, received: event.sequence },
      );
    }

    onEvent(event);
    lastSequence = event.sequence;
    received += 1;
  });

  const cancelReader = () => {
    void reader.cancel().catch(() => undefined);
  };
  signal.addEventListener("abort", cancelReader, { once: true });

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (signal.aborted) throw abortError();
      if (done) {
        parser.push(decoder.decode(), true);
        break;
      }
      parser.push(decoder.decode(value, { stream: true }));
    }
    return { lastSequence, received };
  } catch (error) {
    if (signal.aborted) throw abortError();
    throw error;
  } finally {
    signal.removeEventListener("abort", cancelReader);
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
