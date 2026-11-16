import type {
  AssetView,
  CapabilitiesView,
  ClarificationInput,
  ClarificationView,
  EvidenceView,
  EventPage,
  EventView,
  ExecutionStatus,
  FeedbackBody,
  FeedbackBodyInput,
  HeritagePage,
  HeritageView,
  LiveHealth,
  MetricsView,
  PreflightInput,
  PreflightView,
  ReadyHealth,
  ResultView,
  RunCreateInput,
  RunPage,
  RunView,
  SamplesView,
  SessionCreateInput,
  SessionCreated,
  SessionView,
  SourcesView,
  StepsView,
  WorkflowView,
} from "./schema";

export type AssetListQuery = { limit?: number; offset?: number };
export type HeritageListQuery = {
  q?: string;
  province?: string;
  category?: string;
  has_location?: boolean;
  limit?: number;
  offset?: number;
};
export type RunListQuery = {
  limit?: number;
  offset?: number;
  saved_only?: boolean;
  execution_status?: ExecutionStatus;
};
export type EventHistoryQuery = {
  after?: number;
  limit?: number;
  include_draft?: boolean;
};
export type ResultQuery = { include_intermediate?: boolean };
export type StepsQuery = { include_draft?: boolean };
export type ExportQuery = ResultQuery & { format: "json" | "markdown" };

export type SessionCreationOptions = {
  signal?: AbortSignal;
};

export type StreamRunOptions = {
  signal: AbortSignal;
  onEvent: (event: EventView) => void;
  after?: number;
  include_draft?: boolean;
};

export type StreamReadResult = {
  lastSequence: number;
  received: number;
};

export type ApiDownload = {
  blob: Blob;
  contentType: string;
  filename?: string;
};

/** The implemented FastAPI surface. It intentionally contains no proposed APIs. */
export interface BackendApi {
  setAccessToken(token?: string): void;
  hasAccessToken(): boolean;
  setLiveModelConsent(consented: boolean): void;
  hasLiveModelConsent(): boolean;
  live(signal?: AbortSignal): Promise<LiveHealth>;
  ready(signal?: AbortSignal): Promise<ReadyHealth>;
  capabilities(signal?: AbortSignal): Promise<CapabilitiesView>;
  ensureDemoMode(
    signal?: AbortSignal,
  ): Promise<CapabilitiesView & { model_mode: "demo" }>;
  ensureRunMode(signal?: AbortSignal): Promise<CapabilitiesView>;
  createSession(
    input?: SessionCreateInput,
    options?: SessionCreationOptions,
  ): Promise<SessionCreated>;
  currentSession(signal?: AbortSignal): Promise<SessionView>;
  revokeCurrentSession(signal?: AbortSignal): Promise<void>;
  workflow(signal?: AbortSignal): Promise<WorkflowView>;
  uploadAsset(file: File, signal?: AbortSignal): Promise<AssetView>;
  assets(query?: AssetListQuery, signal?: AbortSignal): Promise<AssetView[]>;
  asset(assetId: string, signal?: AbortSignal): Promise<AssetView>;
  assetContent(assetId: string, signal?: AbortSignal): Promise<Blob>;
  deleteAsset(assetId: string, signal?: AbortSignal): Promise<void>;
  samples(signal?: AbortSignal): Promise<SamplesView>;
  heritages(
    query?: HeritageListQuery,
    signal?: AbortSignal,
  ): Promise<HeritagePage>;
  heritage(heritageId: string, signal?: AbortSignal): Promise<HeritageView>;
  useHeritageMedia(
    heritageId: string,
    mediaId: string,
    signal?: AbortSignal,
  ): Promise<AssetView>;
  useSample(sampleId: string, signal?: AbortSignal): Promise<AssetView>;
  createRun(
    input: RunCreateInput,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<RunView>;
  preflight(
    input: PreflightInput,
    signal?: AbortSignal,
  ): Promise<PreflightView>;
  runs(query?: RunListQuery, signal?: AbortSignal): Promise<RunPage>;
  run(runId: string, signal?: AbortSignal): Promise<RunView>;
  cancelRun(runId: string, signal?: AbortSignal): Promise<RunView>;
  retryRun(
    runId: string,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<RunView>;
  reviewRun(
    runId: string,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<RunView>;
  eventHistory(
    runId: string,
    query?: EventHistoryQuery,
    signal?: AbortSignal,
  ): Promise<EventPage>;
  streamRunEvents(
    runId: string,
    options: StreamRunOptions,
  ): Promise<StreamReadResult>;
  result(
    runId: string,
    query?: ResultQuery,
    signal?: AbortSignal,
  ): Promise<ResultView>;
  evidence(runId: string, signal?: AbortSignal): Promise<EvidenceView>;
  regionImage(
    runId: string,
    regionId: string,
    signal?: AbortSignal,
  ): Promise<Blob>;
  clarification(
    runId: string,
    signal?: AbortSignal,
  ): Promise<ClarificationView>;
  submitClarification(
    runId: string,
    input: ClarificationInput,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<RunView>;
  sources(runId: string, signal?: AbortSignal): Promise<SourcesView>;
  steps(
    runId: string,
    query?: StepsQuery,
    signal?: AbortSignal,
  ): Promise<StepsView>;
  metrics(runId: string, signal?: AbortSignal): Promise<MetricsView>;
  exportRun(
    runId: string,
    query: ExportQuery,
    signal?: AbortSignal,
  ): Promise<ApiDownload>;
  bookmarkRun(
    runId: string,
    saved: boolean,
    signal?: AbortSignal,
  ): Promise<RunView>;
  setFeedback(
    runId: string,
    input: FeedbackBodyInput,
    signal?: AbortSignal,
  ): Promise<FeedbackBody>;
  feedback(runId: string, signal?: AbortSignal): Promise<FeedbackBody>;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status = 0,
    public readonly code = "UNKNOWN",
    public readonly details?: unknown,
    public readonly requestId?: string,
    cause?: unknown,
  ) {
    super(message, cause === undefined ? undefined : { cause });
    this.name = "ApiError";
  }

  /** Snake-case alias matching the server error envelope. */
  get request_id() {
    return this.requestId;
  }
}

export const isApiError = (error: unknown): error is ApiError =>
  error instanceof ApiError;

export type DemoCapabilities = CapabilitiesView & { model_mode: "demo" };

export type RunModeGate =
  | { allowed: true; capabilities: DemoCapabilities }
  | {
      allowed: false;
      code: "MODEL_MODE_UNVERIFIED" | "DEMO_MODE_REQUIRED";
      message: string;
    };

/**
 * Run-producing actions in API integration mode are safe only after this gate
 * observes model_mode=demo from GET /api/v1/capabilities.
 */
export function evaluateDemoModelMode(
  capabilities: CapabilitiesView | null | undefined,
): RunModeGate {
  if (!capabilities) {
    return {
      allowed: false,
      code: "MODEL_MODE_UNVERIFIED",
      message:
        "Không xác minh được chế độ model của backend; thao tác tạo run đã bị chặn.",
    };
  }
  if (capabilities.model_mode !== "demo") {
    return {
      allowed: false,
      code: "DEMO_MODE_REQUIRED",
      message:
        "Backend không ở chế độ demo; thao tác có thể gọi model trả phí đã bị chặn.",
    };
  }
  return { allowed: true, capabilities: capabilities as DemoCapabilities };
}

export function assertDemoModelMode(
  capabilities: CapabilitiesView | null | undefined,
): DemoCapabilities {
  const gate = evaluateDemoModelMode(capabilities);
  if (!gate.allowed) {
    throw new ApiError(gate.message, 409, gate.code);
  }
  return gate.capabilities;
}

export type RunModelOptions = {
  allowLiveModelCalls?: boolean;
  liveModelConsent?: boolean;
};

export type RunExecutionGate =
  | { allowed: true; capabilities: CapabilitiesView }
  | {
      allowed: false;
      code:
        | "MODEL_MODE_UNVERIFIED"
        | "LIVE_MODEL_CALLS_DISABLED"
        | "LIVE_MODEL_CONSENT_REQUIRED"
        | "MODEL_NOT_CONFIGURED";
      message: string;
    };

/** Demo remains the default. Live requires both build opt-in and tab consent. */
export function evaluateRunModelMode(
  capabilities: CapabilitiesView | null | undefined,
  options: RunModelOptions = {},
): RunExecutionGate {
  if (!capabilities || !["demo", "live"].includes(capabilities.model_mode)) {
    return {
      allowed: false,
      code: "MODEL_MODE_UNVERIFIED",
      message:
        "Chưa xác minh được chế độ AI của backend. Hãy kiểm tra lại kết nối.",
    };
  }
  if (capabilities.model_mode === "demo") {
    return { allowed: true, capabilities };
  }
  if (options.allowLiveModelCalls !== true) {
    return {
      allowed: false,
      code: "LIVE_MODEL_CALLS_DISABLED",
      message:
        "Backend đang dùng AI thật. Bản frontend này chưa bật quyền gọi model live.",
    };
  }
  if (!capabilities.model_configured || capabilities.missing_roles.length > 0) {
    return {
      allowed: false,
      code: "MODEL_NOT_CONFIGURED",
      message:
        "Backend chưa cấu hình đủ các model cần thiết. Hãy kiểm tra cấu hình server.",
    };
  }
  if (options.liveModelConsent !== true) {
    return {
      allowed: false,
      code: "LIVE_MODEL_CONSENT_REQUIRED",
      message:
        "Xác nhận sử dụng AI thật trong phiên này trước khi tạo tác vụ có thể tính phí.",
    };
  }
  return { allowed: true, capabilities };
}

export function assertRunModelMode(
  capabilities: CapabilitiesView | null | undefined,
  options: RunModelOptions = {},
): CapabilitiesView {
  const gate = evaluateRunModelMode(capabilities, options);
  if (!gate.allowed) throw new ApiError(gate.message, 409, gate.code);
  return gate.capabilities;
}

export function assertIdempotencyKey(key: string): string {
  const containsControlCharacter = [...key].some((character) => {
    const code = character.charCodeAt(0);
    return code <= 31 || code === 127;
  });
  if (
    key.length < 1 ||
    key.length > 128 ||
    key.trim().length === 0 ||
    containsControlCharacter
  ) {
    throw new ApiError(
      "Idempotency-Key phải có từ 1 đến 128 ký tự an toàn.",
      0,
      "INVALID_IDEMPOTENCY_KEY",
    );
  }
  return key;
}

/** Create once per intended mutation and reuse the returned value for retransmission. */
export function createIdempotencyKey(prefix = "web"): string {
  const safePrefix =
    prefix.replace(/[^A-Za-z0-9._-]/g, "-").slice(0, 32) || "web";
  return assertIdempotencyKey(`${safePrefix}-${crypto.randomUUID()}`);
}

export const isExecutionTerminal = (status: ExecutionStatus) =>
  status === "succeeded" || status === "failed" || status === "cancelled";

/** A pending clarification ends this execution segment without claiming success. */
export const isExecutionSettled = (status: ExecutionStatus) =>
  isExecutionTerminal(status) || status === "awaiting_input";
