import { describe, expect, it, vi } from "vitest";
import { HttpApi } from "../src/api/http";

const ASSET_ID = "22222222-2222-4222-8222-222222222222";
const RUN_ID = "33333333-3333-4333-8333-333333333333";
const NOW = "2026-11-15T00:00:00.000Z";

const capabilities = (modelMode: "demo" | "live" = "demo") => ({
  api_version: "v1",
  config_hash: "fixture-config",
  model_mode: modelMode,
  model_configured: modelMode === "live",
  missing_roles: [],
  max_upload_bytes: 10_000_000,
  max_image_pixels: 20_000_000,
  max_question_characters: 4_000,
  profiles: [
    {
      id: "default",
      workflow_version: "fixture-workflow",
      generation_enabled: false,
    },
  ],
  session_bootstrap_required: false,
});

const runView = {
  run_id: RUN_ID,
  run_kind: "full",
  request_id: "request-fixture",
  trace_id: null,
  asset_id: ASSET_ID,
  parent_run_id: null,
  question: "Giới thiệu di sản trong ảnh",
  audience: "tourist",
  model_mode: "demo",
  execution_status: "queued",
  result_status: null,
  bookmarked: false,
  event_count: 0,
  error_type: null,
  created_at: NOW,
  started_at: null,
  finished_at: null,
  events_url: `/api/v1/runs/${RUN_ID}/events`,
  result_url: `/api/v1/runs/${RUN_ID}/result`,
} as const;

describe("FastAPI HTTP transport", () => {
  it("uses origin health routes and leaves public requests unauthenticated", async () => {
    const fetcher = vi.fn(
      async (input: string | URL | Request, _init?: RequestInit) => {
        void _init;
        const path = new URL(String(input)).pathname;
        if (path === "/health/live") return Response.json({ status: "ok" });
        return Response.json(capabilities());
      },
    );
    const api = new HttpApi({
      baseUrl: "https://agent.example/api/v1",
      accessToken: "short-lived",
      fetch: fetcher as unknown as typeof fetch,
    });

    await expect(api.live()).resolves.toEqual({ status: "ok" });
    await expect(api.ensureDemoMode()).resolves.toMatchObject({
      model_mode: "demo",
    });

    expect(new URL(String(fetcher.mock.calls[0][0])).pathname).toBe(
      "/health/live",
    );
    expect(new URL(String(fetcher.mock.calls[1][0])).pathname).toBe(
      "/api/v1/capabilities",
    );
    for (const call of fetcher.mock.calls) {
      const init = call[1] as RequestInit;
      expect(init.credentials).toBe("omit");
      expect(init.redirect).toBe("error");
      expect(new Headers(init.headers).has("Authorization")).toBe(false);
    }
  });

  it("blocks run-producing calls unless capabilities confirms demo mode", async () => {
    const fetcher = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) => {
        void _input;
        void _init;
        return Response.json(capabilities("live"));
      },
    );
    const api = new HttpApi({
      baseUrl: "https://agent.example/api/v1",
      accessToken: "fixture-token",
      fetch: fetcher as unknown as typeof fetch,
    });

    await expect(
      api.createRun(
        { asset_id: ASSET_ID, question: "Không được gửi" },
        "create-run-1",
      ),
    ).rejects.toMatchObject({ status: 409, code: "LIVE_MODEL_CALLS_DISABLED" });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(new URL(String(fetcher.mock.calls[0][0])).pathname).toBe(
      "/api/v1/capabilities",
    );
  });

  it("sends validated run JSON, bearer ownership and idempotency metadata", async () => {
    const fetcher = vi.fn(
      async (input: string | URL | Request, init?: RequestInit) => {
        void init;
        const path = new URL(String(input)).pathname;
        return path.endsWith("/capabilities")
          ? Response.json(capabilities())
          : Response.json(runView);
      },
    );
    const api = new HttpApi({
      baseUrl: "https://agent.example/api/v1",
      accessToken: "fixture-token",
      fetch: fetcher as unknown as typeof fetch,
    });

    await expect(
      api.createRun(
        { asset_id: ASSET_ID, question: "  Giới thiệu di sản trong ảnh  " },
        "create-run-1",
      ),
    ).resolves.toMatchObject({ run_id: RUN_ID, model_mode: "demo" });

    const [url, init] = fetcher.mock.calls[1] as unknown as [
      string,
      RequestInit,
    ];
    expect(new URL(url).pathname).toBe("/api/v1/runs");
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer fixture-token");
    expect(headers.get("Idempotency-Key")).toBe("create-run-1");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(init.body))).toEqual({
      asset_id: ASSET_ID,
      question: "Giới thiệu di sản trong ảnh",
      audience: "tourist",
      profile: "default",
    });
  });

  it("encodes list queries and rejects protected calls before fetch without a token", async () => {
    const fetcher = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) => {
        void _input;
        void _init;
        return Response.json({ items: [], total: 0, limit: 25, offset: 5 });
      },
    );
    const api = new HttpApi({
      baseUrl: "https://agent.example/api/v1",
      accessToken: "fixture-token",
      fetch: fetcher as unknown as typeof fetch,
    });
    await api.runs({
      limit: 25,
      offset: 5,
      saved_only: true,
      execution_status: "succeeded",
    });
    const url = new URL(String(fetcher.mock.calls[0][0]));
    expect(Object.fromEntries(url.searchParams)).toEqual({
      limit: "25",
      offset: "5",
      saved_only: "true",
      execution_status: "succeeded",
    });

    const unauthenticatedFetch = vi.fn();
    const unauthenticated = new HttpApi({
      baseUrl: "https://agent.example/api/v1",
      fetch: unauthenticatedFetch as unknown as typeof fetch,
    });
    await expect(unauthenticated.currentSession()).rejects.toMatchObject({
      status: 401,
      code: "AUTH_REQUIRED",
    });
    expect(unauthenticatedFetch).not.toHaveBeenCalled();
  });

  it("leaves multipart boundaries to fetch", async () => {
    const fetcher = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) => {
        void _input;
        void _init;
        return Response.json({
          asset_id: ASSET_ID,
          sha256: "a".repeat(64),
          size_bytes: 1,
          width: 1,
          height: 1,
          media_type: "image/png",
          created_at: NOW,
          content_url: `/api/v1/assets/${ASSET_ID}/content`,
        });
      },
    );
    const api = new HttpApi({
      baseUrl: "https://agent.example/api/v1",
      accessToken: "fixture-token",
      fetch: fetcher as unknown as typeof fetch,
    });

    await api.uploadAsset(
      new File([Uint8Array.of(137)], "fixture.png", { type: "image/png" }),
    );
    const init = fetcher.mock.calls[0][1] as RequestInit;
    expect(init.body).toBeInstanceOf(FormData);
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
    expect(new Headers(init.headers).get("Authorization")).toBe(
      "Bearer fixture-token",
    );
  });

  it("surfaces the structured backend error and request correlation ID", async () => {
    const fetcher = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) => {
        void _input;
        void _init;
        return Response.json(
          {
            error: {
              code: "SESSION_EXPIRED",
              message: "Phiên đã hết hạn.",
              request_id: "request-body",
              details: { expired: true },
            },
          },
          { status: 401, headers: { "X-Request-ID": "request-header" } },
        );
      },
    );
    const api = new HttpApi({
      baseUrl: "https://agent.example/api/v1",
      accessToken: "fixture-token",
      fetch: fetcher as unknown as typeof fetch,
    });

    await expect(api.currentSession()).rejects.toMatchObject({
      status: 401,
      code: "SESSION_EXPIRED",
      message: "Phiên đã hết hạn.",
      requestId: "request-body",
      request_id: "request-body",
      details: { expired: true },
    });
  });

  it("rejects incompatible success payloads rather than leaking invalid state", async () => {
    const api = new HttpApi({
      baseUrl: "https://agent.example/api/v1",
      fetch: (async () => Response.json({ status: "ok" })) as typeof fetch,
    });
    await expect(api.capabilities()).rejects.toMatchObject({
      status: 502,
      code: "SCHEMA_MISMATCH",
    });
  });

  it("requires a true 204 revoke response, clears the token and preserves aborts", async () => {
    const fetcher = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) => {
        void _input;
        void _init;
        return new Response(null, { status: 204 });
      },
    );
    const api = new HttpApi({
      baseUrl: "https://agent.example/api/v1",
      accessToken: "fixture-token",
      fetch: fetcher as unknown as typeof fetch,
    });
    await expect(api.revokeCurrentSession()).resolves.toBeUndefined();
    expect(api.hasAccessToken()).toBe(false);

    const controller = new AbortController();
    controller.abort();
    await expect(api.live(controller.signal)).rejects.toMatchObject({
      name: "AbortError",
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
