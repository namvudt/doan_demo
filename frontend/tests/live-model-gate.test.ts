import { describe, expect, it, vi } from "vitest";
import {
  assertDemoModelMode,
  evaluateDemoModelMode,
  evaluateRunModelMode,
} from "../src/api/contracts";
import { HttpApi } from "../src/api/http";
import type { CapabilitiesView, RunView } from "../src/api/schema";

const ASSET_ID = "22222222-2222-4222-8222-222222222222";
const RUN_ID = "33333333-3333-4333-8333-333333333333";
const capabilities = (
  model_mode: "demo" | "live" = "live",
): CapabilitiesView => ({
  api_version: "v1",
  config_hash: "live-gate-fixture",
  model_mode,
  model_configured: true,
  missing_roles: [],
  max_upload_bytes: 10_000_000,
  max_image_pixels: 20_000_000,
  max_question_characters: 4_000,
  profiles: [
    { id: "default", workflow_version: "fixture", generation_enabled: false },
  ],
  session_bootstrap_required: false,
});
const run: RunView = {
  run_id: RUN_ID,
  run_kind: "full",
  request_id: "fixture-request",
  trace_id: null,
  asset_id: ASSET_ID,
  parent_run_id: null,
  question: "Mô tả di sản trong ảnh",
  audience: "tourist",
  model_mode: "live",
  execution_status: "queued",
  result_status: null,
  bookmarked: false,
  event_count: 0,
  error_type: null,
  created_at: "2026-11-15T00:00:00.000Z",
  started_at: null,
  finished_at: null,
  events_url: `/api/v1/runs/${RUN_ID}/events`,
  result_url: `/api/v1/runs/${RUN_ID}/result`,
};

describe("explicit live model consent", () => {
  it("preserves the legacy demo-only gate and default demo journeys", () => {
    expect(evaluateDemoModelMode(capabilities("demo")).allowed).toBe(true);
    expect(evaluateDemoModelMode(capabilities())).toMatchObject({
      allowed: false,
      code: "DEMO_MODE_REQUIRED",
    });
    expect(() => assertDemoModelMode(capabilities())).toThrow();
    expect(evaluateRunModelMode(capabilities("demo"))).toMatchObject({
      allowed: true,
    });
  });

  it("requires both explicit configuration and consent before allowing live calls", () => {
    expect(evaluateRunModelMode(capabilities())).toMatchObject({
      allowed: false,
      code: "LIVE_MODEL_CALLS_DISABLED",
    });
    expect(
      evaluateRunModelMode(capabilities(), { liveModelConsent: true }),
    ).toMatchObject({ allowed: false, code: "LIVE_MODEL_CALLS_DISABLED" });
    expect(
      evaluateRunModelMode(capabilities(), { allowLiveModelCalls: true }),
    ).toMatchObject({ allowed: false, code: "LIVE_MODEL_CONSENT_REQUIRED" });
    expect(
      evaluateRunModelMode(capabilities(), {
        allowLiveModelCalls: true,
        liveModelConsent: true,
      }),
    ).toMatchObject({ allowed: true, capabilities: { model_mode: "live" } });
  });

  it("refuses unverified or incompletely configured live services even with consent", () => {
    const options = { allowLiveModelCalls: true, liveModelConsent: true };
    expect(evaluateRunModelMode(undefined, options)).toMatchObject({
      allowed: false,
      code: "MODEL_MODE_UNVERIFIED",
    });
    expect(evaluateRunModelMode(null, options)).toMatchObject({
      allowed: false,
      code: "MODEL_MODE_UNVERIFIED",
    });
    expect(
      evaluateRunModelMode(
        { ...capabilities(), model_configured: false },
        options,
      ),
    ).toMatchObject({ allowed: false, code: "MODEL_NOT_CONFIGURED" });
    expect(
      evaluateRunModelMode(
        { ...capabilities(), missing_roles: ["visual"] },
        options,
      ),
    ).toMatchObject({ allowed: false, code: "MODEL_NOT_CONFIGURED" });
  });

  it("blocks every run-producing transport action before consent without sending a POST", async () => {
    const fetcher = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) => {
        void _input;
        void _init;
        return Response.json(capabilities());
      },
    );
    const api = new HttpApi({
      baseUrl: "https://agent.example/api/v1",
      accessToken: "fixture-token",
      allowLiveModelCalls: true,
      fetch: fetcher as typeof fetch,
    });
    for (const action of [
      () =>
        api.createRun(
          { asset_id: ASSET_ID, question: run.question },
          "live-create",
        ),
      () => api.retryRun(RUN_ID, "live-retry"),
      () => api.reviewRun(RUN_ID, "live-review"),
    ]) {
      await expect(action()).rejects.toMatchObject({
        status: 409,
        code: "LIVE_MODEL_CONSENT_REQUIRED",
      });
    }
    expect(fetcher).toHaveBeenCalledTimes(3);
    expect(
      fetcher.mock.calls.every(
        ([, init]) => !init?.method || init.method === "GET",
      ),
    ).toBe(true);
  });

  it("sends a live mutation only after opt-in and rechecks current server capabilities", async () => {
    let currentCapabilities = capabilities();
    const fetcher = vi.fn(
      async (input: string | URL | Request, _init?: RequestInit) => {
        void _init;
        return Response.json(
          new URL(String(input)).pathname.endsWith("/capabilities")
            ? currentCapabilities
            : run,
        );
      },
    );
    const api = new HttpApi({
      baseUrl: "https://agent.example/api/v1",
      accessToken: "fixture-token",
      allowLiveModelCalls: true,
      fetch: fetcher as typeof fetch,
    });
    api.setLiveModelConsent(true);
    await expect(
      api.createRun(
        { asset_id: ASSET_ID, question: run.question },
        "live-create",
      ),
    ).resolves.toMatchObject({ model_mode: "live" });
    const sent = fetcher.mock.calls[1][1];
    expect(sent?.method).toBe("POST");
    expect(new Headers(sent?.headers).get("Idempotency-Key")).toBe(
      "live-create",
    );
    expect(JSON.parse(String(sent?.body))).not.toHaveProperty("api_key");
    currentCapabilities = { ...capabilities(), missing_roles: ["judge"] };
    await expect(api.retryRun(RUN_ID, "live-retry")).rejects.toMatchObject({
      code: "MODEL_NOT_CONFIGURED",
    });
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("does not transfer consent to another session or retain it after revocation", async () => {
    const api = new HttpApi({
      baseUrl: "https://agent.example/api/v1",
      accessToken: "first-session",
      allowLiveModelCalls: true,
      fetch: (async () => new Response(null, { status: 204 })) as typeof fetch,
    });
    api.setLiveModelConsent(true);
    api.setAccessToken(" first-session ");
    expect(api.hasLiveModelConsent()).toBe(true);
    api.setAccessToken("second-session");
    expect(api.hasLiveModelConsent()).toBe(false);
    api.setLiveModelConsent(true);
    await api.revokeCurrentSession();
    expect(api.hasAccessToken()).toBe(false);
    expect(api.hasLiveModelConsent()).toBe(false);
  });

  it("allows owner-scoped inspection and cancellation without consenting to new charges", async () => {
    const fetcher = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) => {
        void _input;
        void _init;
        return Response.json(run);
      },
    );
    const api = new HttpApi({
      baseUrl: "https://agent.example/api/v1",
      accessToken: "fixture-token",
      fetch: fetcher as typeof fetch,
    });
    await expect(api.run(RUN_ID)).resolves.toMatchObject({ run_id: RUN_ID });
    await expect(api.cancelRun(RUN_ID)).resolves.toMatchObject({
      run_id: RUN_ID,
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(
      fetcher.mock.calls.map(([input]) => new URL(String(input)).pathname),
    ).toEqual([`/api/v1/runs/${RUN_ID}`, `/api/v1/runs/${RUN_ID}/cancel`]);
  });
});
