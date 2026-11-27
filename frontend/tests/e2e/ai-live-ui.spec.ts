import { expect, test, type Response } from "@playwright/test";
import type {
  MetricsView,
  PreflightView,
  ResultView,
  RunView,
} from "../../src/api/schema";

test.skip(
  !["1", "true"].includes(process.env.RUN_LIVE_UI || ""),
  "Live provider execution requires an explicit RUN_LIVE_UI opt-in.",
);
test.use({ trace: "off", video: "off" });

const consentLabel =
  "Tôi đồng ý gọi AI thật trong phiên này và chấp nhận chi phí phát sinh.";
const terminalStates = new Set(["succeeded", "failed", "cancelled"]);

function label(value: unknown): string | null {
  if (typeof value !== "string") return null;
  // Only identifiers/classifications, never freeform provider messages or bodies.
  return /^[A-Za-z0-9_.:/ -]{1,160}$/.test(value) ? value : null;
}

test("@ai-live one consented UI workflow calls the configured live model", async ({
  page,
}, testInfo) => {
  test.setTimeout(210_000);
  const report: Record<string, unknown> = {
    started_at: new Date().toISOString(),
    test_origin: testInfo.project.use.baseURL,
    intended_runs: 1,
    retry_review_actions: 0,
    model_mode: null,
    outcome: "not_started",
  };
  const requests: { method: string; path: string; status: number }[] = [];
  let token = "";
  let sessionsUrl = "";
  let runId = "";
  let runSnapshot: RunView | undefined;
  let runResult: ResultView | undefined;
  let runMetrics: MetricsView | undefined;
  let createRequests = 0;
  const pageErrors: string[] = [];

  const recordResponse = async (response: Response) => {
    const path = new URL(response.url()).pathname;
    if (!path.startsWith("/api/v1/") && !path.startsWith("/health/")) return;
    requests.push({
      method: response.request().method(),
      path: path.replace(/[0-9a-f]{8}-[0-9a-f-]{27,}/gi, "{id}"),
      status: response.status(),
    });
    if (response.status() !== 200 || !runId) return;
    try {
      if (path.endsWith(`/runs/${runId}`)) runSnapshot = await response.json();
      else if (path.endsWith(`/runs/${runId}/result`))
        runResult = await response.json();
      else if (path.endsWith(`/runs/${runId}/metrics`))
        runMetrics = await response.json();
    } catch {
      /* Report only validated fields after the UI response has completed. */
    }
  };
  page.on("response", (response) => {
    void recordResponse(response);
  });
  page.on("pageerror", (error) => pageErrors.push(error.name));
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname.endsWith("/api/v1/runs")
    )
      createRequests += 1;
  });
  await page.route(/^https?:\/\//, async (route) => {
    const url = new URL(route.request().url());
    if (["127.0.0.1", "localhost"].includes(url.hostname))
      await route.continue();
    else await route.abort("blockedbyclient");
  });

  try {
    const capabilitiesPromise = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname.endsWith("/capabilities") &&
        response.status() === 200,
    );
    await page.goto("/login");
    const capabilities = await (await capabilitiesPromise).json();
    report.model_mode = capabilities.model_mode;
    report.model_configured = capabilities.model_configured;
    report.missing_roles = Array.isArray(capabilities.missing_roles)
      ? capabilities.missing_roles.map(label)
      : [];
    expect(
      capabilities.model_mode,
      "This test must never use demo inference",
    ).toBe("live");
    expect(
      capabilities.model_configured,
      "Configured live credentials are required",
    ).toBe(true);
    expect(capabilities.missing_roles).toEqual([]);
    expect(
      capabilities.session_bootstrap_required,
      "Use an isolated local server without a browser bootstrap secret",
    ).toBe(false);
    await expect(
      page.getByRole("heading", { name: "Truy cập phiên khách" }),
    ).toBeVisible();

    const sessionPromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname.endsWith("/sessions"),
    );
    await page
      .getByRole("button", { name: "Tạo phiên khách", exact: true })
      .click();
    const sessionResponse = await sessionPromise;
    expect(sessionResponse.status()).toBe(201);
    const session = await sessionResponse.json();
    token = session.access_token;
    sessionsUrl = sessionResponse.url();
    await expect(page).toHaveURL(/\/chat$/);
    const createButton = page.getByRole("button", {
      name: "Gửi câu hỏi",
      exact: true,
    });
    await expect(
      createButton,
      "A live workflow must be disabled before session consent",
    ).toBeDisabled();
    const sample = page.getByLabel("Ảnh mẫu từ hệ thống");
    await expect(sample.locator('option[value="chua_mot_cot"]')).toBeAttached();
    await sample.selectOption("chua_mot_cot");
    await page
      .getByRole("textbox", { name: "Câu hỏi", exact: true })
      .fill(
        "Trong phạm vi di sản kiến trúc Việt Nam, hãy mô tả ngắn gọn các chi tiết kiến trúc quan sát trực tiếp trong ảnh này; nêu rõ điểm chưa chắc chắn, không suy đoán lịch sử khi thiếu nguồn.",
      );

    const preflightPromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname.endsWith("/preflight"),
    );
    await page
      .getByRole("button", { name: "Kiểm tra sẵn sàng", exact: true })
      .click();
    const preflightResponse = await preflightPromise;
    report.preflight_http = preflightResponse.status();
    expect(
      preflightResponse.status(),
      "Live metadata preflight must respond successfully before any run is created",
    ).toBe(200);
    const preflight: PreflightView = await preflightResponse.json();
    report.preflight = {
      ready: preflight.ready,
      scope: label(preflight.scope),
      generation_verified: preflight.generation_verified,
      roles: preflight.roles.map((role) => ({
        role: label(role.role),
        provider: label(role.provider),
        model: label(role.model),
        ready: role.ready,
        error_code: label(role.error_code),
        error_category: label(role.error_category),
        provider_status_code: role.provider_status_code,
        provider_reason: label(role.provider_reason),
      })),
    };
    expect(
      preflight.ready,
      "Live metadata preflight failed; inspect the sanitized test attachment",
    ).toBe(true);
    expect(createRequests).toBe(0);
    await page.getByLabel(consentLabel, { exact: true }).check();
    await expect(createButton).toBeEnabled();

    const createPromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname.endsWith("/api/v1/runs"),
    );
    report.outcome = "run_requested";
    await createButton.click();
    const createResponse = await createPromise;
    report.create_http = createResponse.status();
    if (createResponse.status() !== 202) {
      const failed = await createResponse.json().catch(() => ({}));
      report.create_error_code = label(failed.error?.code);
      report.create_request_id = label(failed.error?.request_id);
    }
    expect(
      createResponse.status(),
      "Live run creation failed; inspect its classified error in the attachment",
    ).toBe(202);
    runSnapshot = await createResponse.json();
    runId = runSnapshot!.run_id;
    report.run_id = runId;
    expect(runSnapshot!.model_mode).toBe("live");
    await expect(page).toHaveURL(new RegExp(`/chat/runs/${runId}$`));

    await expect
      .poll(() => terminalStates.has(runSnapshot?.execution_status || ""), {
        timeout: 160_000,
        message: "Waiting for the one live workflow to reach a terminal state",
      })
      .toBe(true);
    report.execution_status = runSnapshot?.execution_status;
    report.error_type = label(runSnapshot?.error_type);
    // Metrics remain inspectable even if generation failed. The browser transport
    // owns authentication; no provider credential or access token is persisted.
    const metricsPromise = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname.endsWith(`/runs/${runId}/metrics`) &&
        response.status() === 200,
    );
    await page.getByRole("button", { name: "Làm mới", exact: true }).click();
    runMetrics = await (await metricsPromise).json();
    report.model_attempts = runMetrics!.calls.map((call) => ({
      role: label(call.agent_role),
      provider: label(call.actual_provider),
      model: label(call.model_used),
      status: label(call.status),
      error_code: label(call.error_code),
      error_category: label(call.error_category),
      provider_status_code:
        typeof call.provider_status_code === "number"
          ? call.provider_status_code
          : null,
      provider_reason: label(call.provider_reason),
    }));
    expect(
      runSnapshot?.execution_status,
      "Live execution ended unsuccessfully; classified attempt metadata is attached",
    ).toBe("succeeded");
    await expect
      .poll(() => Boolean(runResult?.final_response?.trim()), {
        timeout: 10_000,
      })
      .toBe(true);
    expect(runResult?.model_mode).toBe("live");
    expect(runMetrics!.model_mode).toBe("live");
    expect(runMetrics!.calls.length).toBeGreaterThan(0);
    expect(
      runMetrics!.calls.every(
        (call) =>
          typeof call.actual_provider === "string" &&
          call.actual_provider !== "demo",
      ),
    ).toBe(true);
    expect(runMetrics!.calls.some((call) => call.status === "success")).toBe(
      true,
    );
    await expect(
      page.getByText("Câu trả lời cuối", { exact: true }),
    ).toBeVisible();
    report.answer_characters = runResult?.final_response?.length;
    report.result_status = label(runResult?.status);
    report.source_count = runResult?.sources.length;
    expect(
      createRequests,
      "The live test must create exactly one paid workflow",
    ).toBe(1);
    expect(pageErrors).toEqual([]);
    const screenshot = testInfo.outputPath("live-vqa-result.png");
    await page.screenshot({ path: screenshot, fullPage: true });
    await testInfo.attach("live-vqa-result", {
      path: screenshot,
      contentType: "image/png",
    });
    report.outcome = "passed";
  } finally {
    report.created_runs = createRequests;
    report.uncaught_page_errors = pageErrors;
    report.http = requests;
    report.finished_at = new Date().toISOString();
    if (report.outcome !== "passed") report.outcome = "failed";
    if (token && sessionsUrl) {
      try {
        const revoked = await page.request.delete(`${sessionsUrl}/me`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        report.session_revoke_http = revoked.status();
      } catch {
        report.session_revoke_http = "network_error";
      }
    }
    await testInfo.attach("live-ui-sanitized-report", {
      body: Buffer.from(JSON.stringify(report, null, 2)),
      contentType: "application/json",
    });
    if (report.outcome === "passed")
      expect(report.session_revoke_http).toBe(204);
  }
});
