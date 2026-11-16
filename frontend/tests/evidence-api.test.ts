import { describe, expect, it, vi } from "vitest";
import { HttpApi } from "../src/api/http";
import { isExecutionSettled, isExecutionTerminal } from "../src/api/contracts";
import {
  capabilitiesViewSchema,
  focusBoxSchema,
  resultViewSchema,
} from "../src/api/schema";

const RUN = "33333333-3333-4333-8333-333333333333";
const ASSET = "22222222-2222-4222-8222-222222222222";
const NOW = "2026-11-16T00:00:00Z";
const capabilities = (mode: "demo" | "live" = "demo") => ({
  api_version: "v1",
  config_hash: "fixture",
  model_mode: mode,
  model_configured: true,
  missing_roles: [],
  max_upload_bytes: 10000000,
  max_image_pixels: 20000000,
  max_question_characters: 4000,
  profiles: [],
  session_bootstrap_required: false,
  accuracy: {
    enabled: true,
    pilot_region: "Hà Nội",
    max_clarifications: 2,
    recognition: { enabled: true, min_observations: 2, max_status: "probable" },
  },
  features: { heritage_catalog: true },
});
const pending = {
  clarification_id: "clarification_fixture",
  revision: 1,
  reason: "entity_ambiguous",
  question: "Bạn muốn đối chiếu địa điểm nào?",
  options: ["A", "B"],
  rounds: 0,
};
const run = {
  run_id: RUN,
  asset_id: ASSET,
  run_kind: "clarification",
  parent_run_id: RUN,
  request_id: null,
  trace_id: null,
  question: "Câu hỏi gốc",
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
  events_url: `/api/v1/runs/${RUN}/events`,
  result_url: `/api/v1/runs/${RUN}/result`,
};
const legacyResult = {
  run_id: RUN,
  parent_run_id: null,
  run_kind: "full",
  reused_nodes: [],
  upstream_config_hash: null,
  model_mode: "demo",
  status: "reviewed",
  question: "Câu hỏi",
  audience: "tourist",
  final_response: "Câu trả lời",
  sources: [],
  plan: {},
  review: {},
  errors: [],
  duration: 1,
  usage: {},
  intermediate: null,
};
const source = {
  source_id: "wiki_fixture",
  title: "Nguồn fixture",
  url: "https://example.test/reference",
  type: "wiki",
  snippet: "Đoạn tư liệu",
  retrieved_at: NOW,
  revision_id: null,
  content_hash: "hash",
  locator: "chars:0:11",
  publisher: "Fixture",
  annotation_status: "retrieved",
  reviewer: null,
  reviewed_at: null,
  number: 1,
  cited: true,
};

describe("evidence-v2 wire compatibility", () => {
  it("accepts capability accuracy alongside catalog without weakening unknown-key checks", () => {
    expect(capabilitiesViewSchema.parse(capabilities()).accuracy?.enabled).toBe(
      true,
    );
    expect(
      capabilitiesViewSchema.safeParse({ ...capabilities(), unexpected: true })
        .success,
    ).toBe(false);
  });

  it("reads legacy results and actual sparse evidence dictionaries plus source metadata", () => {
    expect(resultViewSchema.safeParse(legacyResult).success).toBe(true);
    const result = resultViewSchema.parse({
      ...legacyResult,
      result_schema_version: 2,
      answer_status: "needs_clarification",
      sources: [source],
      recognition: {
        status: "unrecognized",
        entity_id: null,
        evidence_ids: [],
        explanation: "Chưa đủ đặc điểm",
        name: null,
        basis: null,
        gate_errors: [],
        candidate_support: [],
        assessment: null,
      },
      location_hint: { name: "Hà Nội", provenance: "user" },
      evidence: [
        {
          evidence_id: "visual_fixture",
          kind: "visual",
          text: "Chi tiết nhìn thấy",
          box: null,
          version: "root",
        },
      ],
      claims: [],
      requested_slots: [],
      candidates: [],
      regions: [],
      image_quality: { flags: [] },
      tool_calls: [],
      clarification: pending,
    });
    expect(result.evidence?.[0].source_id).toBeUndefined();
    expect(result.clarification?.options).toEqual(["A", "B"]);
    expect(result.sources[0].locator).toBe("chars:0:11");
  });

  it("stops an awaiting execution segment without declaring it terminal success", () => {
    expect(isExecutionSettled("awaiting_input")).toBe(true);
    expect(isExecutionTerminal("awaiting_input")).toBe(false);
    expect(isExecutionSettled("running")).toBe(false);
    expect(focusBoxSchema.safeParse([0.8, 0.1, 0.2, 0.9]).success).toBe(false);
  });

  it("uses owned evidence/clarification/region endpoints and validates PNG content", async () => {
    const fetcher = vi.fn(
      async (input: string | URL | Request, init?: RequestInit) => {
        const path = new URL(String(input)).pathname;
        expect(new Headers(init?.headers).get("Authorization")).toBe(
          "Bearer owner-token",
        );
        if (path.endsWith("/clarification"))
          return Response.json({
            run_id: RUN,
            execution_status: "awaiting_input",
            clarification: pending,
            continuation_run_id: null,
          });
        if (path.endsWith("/image"))
          return new Response(new Uint8Array([1, 2]), {
            headers: { "Content-Type": "image/png" },
          });
        return Response.json({
          run_id: RUN,
          result_schema_version: 2,
          answer_status: "needs_clarification",
          recognition: null,
          location_hint: null,
          evidence: [],
          claims: [],
          requested_slots: [],
          candidates: [],
          image_quality: {},
          regions: [],
          tool_calls: [],
        });
      },
    );
    const api = new HttpApi({
      baseUrl: "https://backend.test/api/v1",
      accessToken: "owner-token",
      fetch: fetcher as typeof fetch,
    });
    expect((await api.evidence(RUN)).answer_status).toBe("needs_clarification");
    expect((await api.clarification(RUN)).clarification?.revision).toBe(1);
    expect((await api.regionImage(RUN, "region_fixture")).type).toBe(
      "image/png",
    );
    expect(
      fetcher.mock.calls.map((call) => new URL(String(call[0])).pathname),
    ).toEqual([
      `/api/v1/runs/${RUN}/evidence`,
      `/api/v1/runs/${RUN}/clarification`,
      `/api/v1/runs/${RUN}/regions/region_fixture/image`,
    ]);
  });

  it("submits a structured child continuation with a stable idempotency key and no rewritten question", async () => {
    const fetcher = vi.fn(
      async (input: string | URL | Request, init?: RequestInit) => {
        if (new URL(String(input)).pathname.endsWith("/capabilities"))
          return Response.json(capabilities());
        expect(new Headers(init?.headers).get("Idempotency-Key")).toBe(
          "clarification-intent",
        );
        expect(JSON.parse(String(init?.body))).toEqual({
          clarification_id: pending.clarification_id,
          revision: 1,
          answer: "",
          selected_candidate: "A",
        });
        return Response.json(run);
      },
    );
    const api = new HttpApi({
      baseUrl: "https://backend.test/api/v1",
      accessToken: "owner-token",
      fetch: fetcher as typeof fetch,
    });
    expect(
      (
        await api.submitClarification(
          RUN,
          {
            clarification_id: pending.clarification_id,
            revision: 1,
            selected_candidate: "A",
          },
          "clarification-intent",
        )
      ).run_kind,
    ).toBe("clarification");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("blocks live clarification until both build opt-in and explicit session consent", async () => {
    const fetcher = vi.fn(async (input: string | URL | Request) =>
      new URL(String(input)).pathname.endsWith("/capabilities")
        ? Response.json(capabilities("live"))
        : Response.json({ ...run, model_mode: "live" }),
    );
    const body = {
      clarification_id: pending.clarification_id,
      revision: 1,
      answer: "Thông tin",
    };
    const locked = new HttpApi({
      baseUrl: "https://backend.test/api/v1",
      accessToken: "owner-token",
      fetch: fetcher as typeof fetch,
    });
    await expect(
      locked.submitClarification(RUN, body, "intent"),
    ).rejects.toMatchObject({ code: "LIVE_MODEL_CALLS_DISABLED" });
    const enabled = new HttpApi({
      baseUrl: "https://backend.test/api/v1",
      accessToken: "owner-token",
      fetch: fetcher as typeof fetch,
      allowLiveModelCalls: true,
    });
    await expect(
      enabled.submitClarification(RUN, body, "intent"),
    ).rejects.toMatchObject({ code: "LIVE_MODEL_CONSENT_REQUIRED" });
    expect(
      fetcher.mock.calls.every((call) =>
        new URL(String(call[0])).pathname.endsWith("/capabilities"),
      ),
    ).toBe(true);
    enabled.setLiveModelConsent(true);
    await expect(
      enabled.submitClarification(RUN, body, "intent"),
    ).resolves.toMatchObject({ run_kind: "clarification" });
  });

  it("rejects empty clarification or invalid region responses before consuming a run", async () => {
    const fetcher = vi.fn(async (input: string | URL | Request) =>
      new URL(String(input)).pathname.endsWith("/capabilities")
        ? Response.json(capabilities())
        : new Response("html", { headers: { "Content-Type": "text/html" } }),
    );
    const api = new HttpApi({
      baseUrl: "https://backend.test/api/v1",
      accessToken: "owner-token",
      fetch: fetcher as typeof fetch,
    });
    await expect(
      api.submitClarification(
        RUN,
        {
          clarification_id: pending.clarification_id,
          revision: 1,
          answer: " ",
        },
        "intent",
      ),
    ).rejects.toMatchObject({ code: "INVALID_REQUEST" });
    expect(fetcher).toHaveBeenCalledTimes(1);
    await expect(api.regionImage(RUN, "region_fixture")).rejects.toMatchObject({
      code: "INVALID_REGION_CONTENT",
    });
  });
});
