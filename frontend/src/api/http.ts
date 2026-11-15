import { z } from "zod";
import {
  ApiError,
  assertDemoModelMode,
  assertRunModelMode,
  assertIdempotencyKey,
  type ApiDownload,
  type AssetListQuery,
  type BackendApi,
  type EventHistoryQuery,
  type ExportQuery,
  type ResultQuery,
  type RunListQuery,
  type SessionCreationOptions,
  type StepsQuery,
  type StreamRunOptions,
} from "./contracts";
import {
  assetViewSchema,
  bookmarkBodySchema,
  capabilitiesViewSchema,
  errorResponseSchema,
  eventPageSchema,
  feedbackBodySchema,
  liveHealthSchema,
  metricsViewSchema,
  preflightBodySchema,
  preflightViewSchema,
  readyHealthSchema,
  resultViewSchema,
  runCreateSchema,
  runPageSchema,
  runViewSchema,
  samplesViewSchema,
  sessionCreateSchema,
  sessionCreatedSchema,
  sessionViewSchema,
  sourcesViewSchema,
  stepsViewSchema,
  workflowViewSchema,
  type PreflightInput,
  type RunCreateInput,
  type SessionCreateInput,
} from "./schema";
import { readEventStream } from "./sse";

export type ApiConnection = {
  /** API prefix, normally /api/v1 or https://host.example/api/v1. */
  baseUrl: string;
  /** Session bearer token; retained only in this HttpApi instance. */
  accessToken?: string;
  /** @deprecated Compatibility alias for accessToken. */
  token?: string;
  timeoutMs?: number;
  /** Explicit public build opt-in; still requires tab-local user consent. */
  allowLiveModelCalls?: boolean;
  /** Test hook; production code should use the browser fetch implementation. */
  fetch?: typeof globalThis.fetch;
};

/** @deprecated Use ApiConnection. */
export type Connection = ApiConnection;

type AuthPolicy = "none" | "session";
type UrlScope = "api" | "origin";
type RequestOptions = Omit<RequestInit, "signal"> & {
  signal?: AbortSignal;
  auth?: AuthPolicy;
  scope?: UrlScope;
  timeout?: boolean;
};

const runtimeBaseUrl = () => {
  if (typeof document !== "undefined" && document.baseURI)
    return document.baseURI;
  if (typeof location !== "undefined" && location.href) return location.href;
  return "http://localhost/";
};

const queryString = (query: Record<string, unknown> = {}) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const text = params.toString();
  return text ? `?${text}` : "";
};

const parseFilename = (contentDisposition: string | null) => {
  if (!contentDisposition) return undefined;
  const extended = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plain = contentDisposition.match(/filename="?([^";]+)"?/i)?.[1];
  const value = extended ? decodeURIComponent(extended) : plain;
  return value?.split(/[\\/]/).pop();
};

const abortError = () =>
  new DOMException("The operation was aborted.", "AbortError");

export class HttpApi implements BackendApi {
  private readonly apiBase: URL;
  private readonly timeoutMs: number;
  private readonly fetchOverride?: typeof globalThis.fetch;
  private accessToken?: string;
  private readonly allowLiveModelCalls: boolean;
  private liveModelConsent = false;

  constructor(connection: ApiConnection) {
    const base = new URL(connection.baseUrl, runtimeBaseUrl());
    if (base.protocol !== "http:" && base.protocol !== "https:") {
      throw new ApiError(
        "API URL phải sử dụng HTTP hoặc HTTPS.",
        0,
        "INVALID_API_URL",
      );
    }
    if (base.username || base.password) {
      throw new ApiError(
        "Không được đặt credential trong API URL.",
        0,
        "INVALID_API_URL",
      );
    }
    base.search = "";
    base.hash = "";
    if (!base.pathname.endsWith("/")) base.pathname += "/";

    this.apiBase = base;
    this.timeoutMs = connection.timeoutMs ?? 30_000;
    this.fetchOverride = connection.fetch;
    this.allowLiveModelCalls = connection.allowLiveModelCalls === true;
    this.setAccessToken(connection.accessToken ?? connection.token);
  }

  setAccessToken(token?: string) {
    const normalized = token?.trim();
    const containsControlCharacter = normalized
      ? [...normalized].some((character) => {
          const code = character.charCodeAt(0);
          return code <= 31 || code === 127;
        })
      : false;
    if (normalized && containsControlCharacter) {
      throw new ApiError(
        "Bearer token không hợp lệ.",
        0,
        "INVALID_ACCESS_TOKEN",
      );
    }
    const nextToken = normalized || undefined;
    if (!nextToken || nextToken !== this.accessToken)
      this.liveModelConsent = false;
    this.accessToken = nextToken;
  }

  hasAccessToken() {
    return Boolean(this.accessToken);
  }

  setLiveModelConsent(consented: boolean) {
    this.liveModelConsent = this.allowLiveModelCalls && consented;
  }

  hasLiveModelConsent() {
    return this.liveModelConsent;
  }

  private url(path: string, scope: UrlScope = "api") {
    const normalizedPath = path.replace(/^\/+/, "");
    if (scope === "origin") {
      return new URL(`/${normalizedPath}`, this.apiBase.origin);
    }
    const url = new URL(normalizedPath, this.apiBase);
    if (
      url.origin !== this.apiBase.origin ||
      !url.pathname.startsWith(this.apiBase.pathname)
    ) {
      throw new ApiError(
        "Đường dẫn API nằm ngoài origin/prefix đã cấu hình.",
        0,
        "UNSAFE_API_URL",
      );
    }
    return url;
  }

  private authenticatedHeaders(url: URL, headers: Headers, auth: AuthPolicy) {
    if (auth === "none") return headers;
    if (!this.accessToken) {
      throw new ApiError(
        "Cần phiên guest hợp lệ để gọi endpoint này.",
        401,
        "AUTH_REQUIRED",
      );
    }
    // Never attach the bearer token to a URL outside the configured API prefix,
    // even when an untrusted response contains an absolute content URL.
    if (
      url.origin !== this.apiBase.origin ||
      !url.pathname.startsWith(this.apiBase.pathname)
    ) {
      throw new ApiError(
        "Đã chặn gửi Authorization ra ngoài API origin.",
        0,
        "UNSAFE_AUTH_ORIGIN",
      );
    }
    headers.set("Authorization", `Bearer ${this.accessToken}`);
    return headers;
  }

  private async fetchResponse(path: string, options: RequestOptions = {}) {
    const {
      auth = "session",
      scope = "api",
      timeout = true,
      signal: externalSignal,
      ...init
    } = options;
    const url = this.url(path, scope);
    const headers = this.authenticatedHeaders(
      url,
      new Headers(init.headers),
      auth,
    );
    if (externalSignal?.aborted) throw abortError();
    const controller = new AbortController();
    let timedOut = false;
    const abortFromCaller = () => controller.abort();
    if (externalSignal?.aborted) controller.abort();
    else
      externalSignal?.addEventListener("abort", abortFromCaller, {
        once: true,
      });
    const timer = timeout
      ? setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, this.timeoutMs)
      : undefined;

    try {
      const fetcher = this.fetchOverride ?? globalThis.fetch.bind(globalThis);
      const response = await fetcher(url.toString(), {
        ...init,
        headers,
        signal: controller.signal,
        credentials: "omit",
        redirect: "error",
      });
      if (externalSignal?.aborted) throw abortError();
      if (timedOut)
        throw new DOMException("Request timed out.", "TimeoutError");
      return response;
    } catch (error) {
      if (externalSignal?.aborted) throw abortError();
      if (timedOut) {
        throw new ApiError(
          "API phản hồi quá thời gian cho phép.",
          408,
          "TIMEOUT",
          undefined,
          undefined,
          error,
        );
      }
      if (error instanceof ApiError) throw error;
      if (error instanceof TypeError) {
        throw new ApiError(
          "Không kết nối được backend. Kiểm tra URL, CORS và trạng thái server.",
          0,
          "NETWORK_ERROR",
          undefined,
          undefined,
          error,
        );
      }
      throw error;
    } finally {
      if (timer !== undefined) clearTimeout(timer);
      externalSignal?.removeEventListener("abort", abortFromCaller);
    }
  }

  private async checkResponse(response: Response) {
    if (response.ok) return;
    const requestId = response.headers.get("X-Request-ID") ?? undefined;
    const text = await response.text().catch(() => "");
    let payload: unknown;
    try {
      payload = text ? JSON.parse(text) : null;
    } catch {
      payload = null;
    }
    const parsed = errorResponseSchema.safeParse(payload);
    if (parsed.success) {
      const detail = parsed.data.error;
      throw new ApiError(
        detail.message,
        response.status,
        detail.code,
        detail.details,
        detail.request_id || requestId,
      );
    }
    throw new ApiError(
      `Yêu cầu backend thất bại (HTTP ${response.status}).`,
      response.status,
      "HTTP_ERROR",
      undefined,
      requestId,
    );
  }

  private async requestJson<S extends z.ZodTypeAny>(
    path: string,
    schema: S,
    options: RequestOptions = {},
  ): Promise<z.output<S>> {
    const headers = new Headers(options.headers);
    if (!headers.has("Accept")) headers.set("Accept", "application/json");
    const response = await this.fetchResponse(path, { ...options, headers });
    await this.checkResponse(response);
    const requestId = response.headers.get("X-Request-ID") ?? undefined;
    const text = await response.text();
    let payload: unknown;
    try {
      payload = text ? JSON.parse(text) : undefined;
    } catch (cause) {
      throw new ApiError(
        "Backend trả JSON không hợp lệ.",
        502,
        "INVALID_RESPONSE",
        undefined,
        requestId,
        cause,
      );
    }
    const parsed = schema.safeParse(payload);
    if (!parsed.success) {
      throw new ApiError(
        "Dữ liệu backend không khớp hợp đồng hiện hành.",
        502,
        "SCHEMA_MISMATCH",
        parsed.error.flatten(),
        requestId,
      );
    }
    return parsed.data;
  }

  private async requestVoid(path: string, options: RequestOptions = {}) {
    const response = await this.fetchResponse(path, options);
    await this.checkResponse(response);
    if (response.status !== 204) {
      throw new ApiError(
        "Backend phải trả HTTP 204 cho thao tác này.",
        502,
        "SCHEMA_MISMATCH",
        { status: response.status },
        response.headers.get("X-Request-ID") ?? undefined,
      );
    }
  }

  private async requestDownload(
    path: string,
    options: RequestOptions = {},
  ): Promise<ApiDownload> {
    const response = await this.fetchResponse(path, options);
    await this.checkResponse(response);
    return {
      blob: await response.blob(),
      contentType:
        response.headers.get("Content-Type") ?? "application/octet-stream",
      filename: parseFilename(response.headers.get("Content-Disposition")),
    };
  }

  private json(
    method: string,
    body?: unknown,
    idempotencyKey?: string,
  ): RequestOptions {
    const headers = new Headers({ "Content-Type": "application/json" });
    if (idempotencyKey) {
      headers.set("Idempotency-Key", assertIdempotencyKey(idempotencyKey));
    }
    return {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    };
  }

  private parseInput<S extends z.ZodTypeAny>(
    schema: S,
    input: unknown,
  ): z.output<S> {
    const parsed = schema.safeParse(input);
    if (!parsed.success) {
      throw new ApiError(
        "Dữ liệu gửi lên backend không hợp lệ.",
        0,
        "INVALID_REQUEST",
        parsed.error.flatten(),
      );
    }
    return parsed.data;
  }

  live = (signal?: AbortSignal) =>
    this.requestJson("health/live", liveHealthSchema, {
      auth: "none",
      scope: "origin",
      signal,
    });

  ready = (signal?: AbortSignal) =>
    this.requestJson("health/ready", readyHealthSchema, {
      auth: "none",
      scope: "origin",
      signal,
    });

  capabilities = (signal?: AbortSignal) =>
    this.requestJson("capabilities", capabilitiesViewSchema, {
      auth: "none",
      signal,
    });

  async ensureDemoMode(signal?: AbortSignal) {
    return assertDemoModelMode(await this.capabilities(signal));
  }

  async ensureRunMode(signal?: AbortSignal) {
    return assertRunModelMode(await this.capabilities(signal), {
      allowLiveModelCalls: this.allowLiveModelCalls,
      liveModelConsent: this.liveModelConsent,
    });
  }

  createSession(
    input: SessionCreateInput = {},
    options: SessionCreationOptions = {},
  ) {
    const body = this.parseInput(sessionCreateSchema, input);
    const init = this.json("POST", body);
    init.auth = "none";
    init.signal = options.signal;
    // Deliberately no X-Bootstrap-Token support in browser code. When
    // capabilities.session_bootstrap_required is true, attach an
    // operator-issued guest access token instead.
    return this.requestJson("sessions", sessionCreatedSchema, init);
  }

  currentSession = (signal?: AbortSignal) =>
    this.requestJson("sessions/me", sessionViewSchema, { signal });

  async revokeCurrentSession(signal?: AbortSignal) {
    await this.requestVoid("sessions/me", { method: "DELETE", signal });
    this.setAccessToken(undefined);
  }

  workflow = (signal?: AbortSignal) =>
    this.requestJson("workflow", workflowViewSchema, { signal });

  uploadAsset(file: File, signal?: AbortSignal) {
    const body = new FormData();
    body.set("file", file);
    return this.requestJson("assets", assetViewSchema, {
      method: "POST",
      body,
      signal,
    });
  }

  assets(query: AssetListQuery = {}, signal?: AbortSignal) {
    return this.requestJson(
      `assets${queryString(query)}`,
      z.array(assetViewSchema),
      { signal },
    );
  }

  asset(assetId: string, signal?: AbortSignal) {
    return this.requestJson(
      `assets/${encodeURIComponent(assetId)}`,
      assetViewSchema,
      {
        signal,
      },
    );
  }

  async assetContent(assetId: string, signal?: AbortSignal) {
    const download = await this.requestDownload(
      `assets/${encodeURIComponent(assetId)}/content`,
      {
        headers: { Accept: "image/png" },
        signal,
      },
    );
    if (!download.contentType.toLowerCase().startsWith("image/png")) {
      throw new ApiError(
        "Backend trả nội dung asset không đúng định dạng PNG.",
        502,
        "INVALID_ASSET_CONTENT",
        { content_type: download.contentType },
      );
    }
    return download.blob;
  }

  deleteAsset(assetId: string, signal?: AbortSignal) {
    return this.requestVoid(`assets/${encodeURIComponent(assetId)}`, {
      method: "DELETE",
      signal,
    });
  }

  samples = (signal?: AbortSignal) =>
    this.requestJson("samples", samplesViewSchema, { auth: "none", signal });

  useSample(sampleId: string, signal?: AbortSignal) {
    return this.requestJson(
      `samples/${encodeURIComponent(sampleId)}/assets`,
      assetViewSchema,
      { method: "POST", signal },
    );
  }

  async createRun(
    input: RunCreateInput,
    idempotencyKey: string,
    signal?: AbortSignal,
  ) {
    await this.ensureRunMode(signal);
    const body = this.parseInput(runCreateSchema, input);
    return this.requestJson("runs", runViewSchema, {
      ...this.json("POST", body, idempotencyKey),
      signal,
    });
  }

  preflight(input: PreflightInput, signal?: AbortSignal) {
    const body = this.parseInput(preflightBodySchema, input);
    return this.requestJson("preflight", preflightViewSchema, {
      ...this.json("POST", body),
      signal,
    });
  }

  runs(query: RunListQuery = {}, signal?: AbortSignal) {
    return this.requestJson(`runs${queryString(query)}`, runPageSchema, {
      signal,
    });
  }

  run(runId: string, signal?: AbortSignal) {
    return this.requestJson(
      `runs/${encodeURIComponent(runId)}`,
      runViewSchema,
      {
        signal,
      },
    );
  }

  cancelRun(runId: string, signal?: AbortSignal) {
    return this.requestJson(
      `runs/${encodeURIComponent(runId)}/cancel`,
      runViewSchema,
      { method: "POST", signal },
    );
  }

  async retryRun(runId: string, idempotencyKey: string, signal?: AbortSignal) {
    await this.ensureRunMode(signal);
    return this.requestJson(
      `runs/${encodeURIComponent(runId)}/retry`,
      runViewSchema,
      { ...this.json("POST", undefined, idempotencyKey), signal },
    );
  }

  async reviewRun(runId: string, idempotencyKey: string, signal?: AbortSignal) {
    await this.ensureRunMode(signal);
    return this.requestJson(
      `runs/${encodeURIComponent(runId)}/review`,
      runViewSchema,
      { ...this.json("POST", undefined, idempotencyKey), signal },
    );
  }

  eventHistory(
    runId: string,
    query: EventHistoryQuery = {},
    signal?: AbortSignal,
  ) {
    return this.requestJson(
      `runs/${encodeURIComponent(runId)}/events/history${queryString(query)}`,
      eventPageSchema,
      { signal },
    );
  }

  async streamRunEvents(runId: string, options: StreamRunOptions) {
    const after = options.after ?? 0;
    if (!Number.isInteger(after) || after < 0) {
      throw new ApiError("SSE cursor không hợp lệ.", 0, "INVALID_CURSOR");
    }
    const response = await this.fetchResponse(
      `runs/${encodeURIComponent(runId)}/events${queryString({
        after,
        include_draft: options.include_draft,
      })}`,
      {
        headers: {
          Accept: "text/event-stream",
          "Last-Event-ID": String(after),
        },
        signal: options.signal,
        timeout: false,
      },
    );
    await this.checkResponse(response);
    return readEventStream(response, {
      signal: options.signal,
      onEvent: options.onEvent,
      after,
    });
  }

  result(runId: string, query: ResultQuery = {}, signal?: AbortSignal) {
    return this.requestJson(
      `runs/${encodeURIComponent(runId)}/result${queryString(query)}`,
      resultViewSchema,
      { signal },
    );
  }

  sources(runId: string, signal?: AbortSignal) {
    return this.requestJson(
      `runs/${encodeURIComponent(runId)}/sources`,
      sourcesViewSchema,
      { signal },
    );
  }

  steps(runId: string, query: StepsQuery = {}, signal?: AbortSignal) {
    return this.requestJson(
      `runs/${encodeURIComponent(runId)}/steps${queryString(query)}`,
      stepsViewSchema,
      { signal },
    );
  }

  metrics(runId: string, signal?: AbortSignal) {
    return this.requestJson(
      `runs/${encodeURIComponent(runId)}/metrics`,
      metricsViewSchema,
      { signal },
    );
  }

  exportRun(runId: string, query: ExportQuery, signal?: AbortSignal) {
    return this.requestDownload(
      `runs/${encodeURIComponent(runId)}/export${queryString(query)}`,
      { signal },
    );
  }

  bookmarkRun(runId: string, saved: boolean, signal?: AbortSignal) {
    const body = this.parseInput(bookmarkBodySchema, { saved });
    return this.requestJson(
      `runs/${encodeURIComponent(runId)}/bookmark`,
      runViewSchema,
      { ...this.json("PUT", body), signal },
    );
  }

  setFeedback(
    runId: string,
    input: z.input<typeof feedbackBodySchema>,
    signal?: AbortSignal,
  ) {
    const body = this.parseInput(feedbackBodySchema, input);
    return this.requestJson(
      `runs/${encodeURIComponent(runId)}/feedback`,
      feedbackBodySchema,
      { ...this.json("PUT", body), signal },
    );
  }

  feedback(runId: string, signal?: AbortSignal) {
    return this.requestJson(
      `runs/${encodeURIComponent(runId)}/feedback`,
      feedbackBodySchema,
      { signal },
    );
  }
}

export { HttpApi as BackendHttpApi };
