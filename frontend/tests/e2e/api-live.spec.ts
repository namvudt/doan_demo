import { fileURLToPath } from "node:url";
import { readFile } from "node:fs/promises";
import { expect, test, type Page, type Response } from "@playwright/test";
import type { RunView } from "../../src/api/schema";

test.skip(
  process.env.RUN_API_INTEGRATION !== "1",
  "Set RUN_API_INTEGRATION=1 only for an isolated backend in demo mode.",
);

type GuestSession = { token: string; sessionsUrl: string; revoked: boolean };
const question = "Đây là di sản nào và có ý nghĩa gì?";
const completedResults = new WeakMap<Page, Set<string>>();

function waitForApi(
  page: Page,
  path: string | RegExp,
  method = "GET",
  status = 200,
) {
  return page.waitForResponse((response: Response) => {
    const pathname = new URL(response.url()).pathname;
    return (
      (typeof path === "string"
        ? pathname.endsWith(path)
        : path.test(pathname)) &&
      response.request().method() === method &&
      response.status() === status
    );
  });
}

async function guestLogin(page: Page): Promise<GuestSession> {
  const capabilitiesPromise = waitForApi(page, "/capabilities");
  await page.goto("/login");
  const capabilities = await (await capabilitiesPromise).json();
  expect(capabilities.model_mode).toBe("demo");
  test.skip(
    capabilities.session_bootstrap_required,
    "This API requires operator-issued access; the browser must not receive a bootstrap secret.",
  );
  await expect(
    page.getByRole("heading", { name: "Truy cập phiên khách" }),
  ).toBeVisible();
  await expect(page.getByText("UI Preview", { exact: false })).toHaveCount(0);
  const sessionPromise = waitForApi(page, /\/sessions$/, "POST", 201);
  await page.getByRole("button", { name: "Tạo phiên khách" }).click();
  const sessionResponse = await sessionPromise;
  const session = await sessionResponse.json();
  await expect(page).toHaveURL(/\/chat$/);
  await expect(
    page.getByRole("heading", { name: "Hỏi backend bằng một ảnh" }),
  ).toBeVisible();
  // Ephemeral tokens stay in memory and are never included in assertions.
  return {
    token: session.access_token as string,
    sessionsUrl: sessionResponse.url(),
    revoked: false,
  };
}

async function revokeSession(page: Page, session: GuestSession) {
  if (session.revoked || !session.token) return;
  await page.request.delete(`${session.sessionsUrl}/me`, {
    headers: { Authorization: `Bearer ${session.token}` },
  });
  session.token = "";
  session.revoked = true;
}

async function finishRun(page: Page, runId: string) {
  await expect(page).toHaveURL(new RegExp(`/chat/runs/${runId}$`));
  await expect
    .poll(() => completedResults.get(page)?.has(runId), { timeout: 20_000 })
    .toBe(true);
  await expect(page.getByText("Đã chạy xong", { exact: true })).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.getByText("Câu trả lời cuối", { exact: true }),
  ).toBeVisible();
  await expect(page.getByAltText("Ảnh đầu vào của run")).toBeVisible();
  await expect
    .poll(() =>
      page.getByAltText("Ảnh đầu vào của run").evaluate((image) => {
        const img = image as HTMLImageElement;
        return img.complete && img.naturalWidth > 0;
      }),
    )
    .toBe(true);
}

async function navigateInApp(page: Page, path: string) {
  await page.evaluate((nextPath) => {
    window.history.pushState(null, "", nextPath);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);
}

test.beforeEach(async ({ page }) => {
  completedResults.set(page, new Set());
  page.on("response", (response) => {
    const match = new URL(response.url()).pathname.match(
      /\/runs\/([^/]+)\/result$/,
    );
    if (match && response.status() === 200)
      completedResults.get(page)?.add(match[1]);
  });
  await page.route(/^https?:\/\//, async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname === "127.0.0.1" || url.hostname === "localhost")
      await route.continue();
    else await route.abort("blockedbyclient");
  });
});

test("@api real demo sample VQA, evidence, feedback, exports, retry and Judge-only review", async ({
  page,
}) => {
  test.setTimeout(90_000);
  const guest = await guestLogin(page);
  try {
    await page.getByRole("button", { name: "Mở trạng thái kết nối" }).click();
    await expect(
      page.getByText("Backend local đã sẵn sàng", { exact: true }),
    ).toBeVisible();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Đóng", exact: true })
      .last()
      .click();
    const sample = page.getByLabel("Sample thật từ backend");
    await expect(sample.locator("option").nth(1)).toBeAttached();
    await sample.selectOption({ index: 1 });
    await page.getByLabel("Câu hỏi").fill(question);
    const preflightPromise = waitForApi(page, "/preflight", "POST");
    await page.getByRole("button", { name: "Kiểm tra sẵn sàng" }).click();
    const preflight = await (await preflightPromise).json();
    expect(preflight.ready).toBe(true);
    expect(preflight.scope).toBe("offline_demo");

    const createPromise = waitForApi(page, /\/runs$/, "POST", 202);
    await page.getByRole("button", { name: "Tạo run" }).click();
    const createResponse = await createPromise;
    const original: RunView = await createResponse.json();
    expect(original.model_mode).toBe("demo");
    expect(original.run_kind).toBe("full");
    expect(original.parent_run_id).toBeNull();
    expect(createResponse.request().headers()["idempotency-key"]).toBeTruthy();
    await finishRun(page, original.run_id);

    const paths = ["result", "events/history", "sources", "steps", "metrics"];
    const promises = paths.map((path) =>
      waitForApi(page, `/runs/${original.run_id}/${path}`),
    );
    await page.getByRole("button", { name: "Làm mới", exact: true }).click();
    const [result, history, sources, steps, metrics] = await Promise.all(
      promises.map(async (responsePromise) => (await responsePromise).json()),
    );
    expect(result.model_mode).toBe("demo");
    expect(result.final_response).toBeTruthy();
    expect(result.status).toBe("reviewed");
    expect(history.terminal).toBe(true);
    expect(history.items.length).toBeGreaterThan(0);
    expect(
      new Set(history.items.map((item: { sequence: number }) => item.sequence))
        .size,
    ).toBe(history.items.length);
    expect(sources.items.length).toBeGreaterThan(0);
    expect(Object.keys(steps.items)).toContain("judge");
    expect(metrics.calls.length).toBeGreaterThan(0);
    expect(
      metrics.calls.every(
        (call: { actual_provider: string }) => call.actual_provider === "demo",
      ),
    ).toBe(true);
    await expect(page.locator(".source-cards article")).toHaveCount(
      sources.items.length,
    );

    const bookmarkPromise = waitForApi(
      page,
      `/runs/${original.run_id}/bookmark`,
      "PUT",
    );
    await page.getByRole("button", { name: "Lưu run", exact: true }).click();
    expect((await (await bookmarkPromise).json()).bookmarked).toBe(true);
    await expect(
      page.getByRole("button", { name: "Bỏ lưu run" }),
    ).toBeVisible();
    const feedbackPromise = waitForApi(
      page,
      `/runs/${original.run_id}/feedback`,
      "PUT",
    );
    await page
      .getByLabel("Ghi chú phản hồi")
      .fill("Kiểm thử Docker API demo cô lập.");
    await page.getByRole("button", { name: "Hữu ích", exact: true }).click();
    const feedback = await (await feedbackPromise).json();
    expect(feedback.rating).toBe("helpful");
    expect(feedback.note).toBe("Kiểm thử Docker API demo cô lập.");

    for (const [name, extension] of [
      ["JSON", ".json"],
      ["Markdown", ".md"],
    ]) {
      const exportPromise = waitForApi(page, `/runs/${original.run_id}/export`);
      const downloadPromise = page.waitForEvent("download");
      await page.getByRole("button", { name, exact: true }).click();
      const download = await downloadPromise;
      expect(download.suggestedFilename()).toBe(
        `heritage-${original.run_id}${extension}`,
      );
      const exported = await exportPromise;
      expect(exported.headers()["content-disposition"]).toContain("attachment");
      const artifactPath = await download.path();
      expect(artifactPath).not.toBeNull();
      const artifact = await readFile(artifactPath!, "utf8");
      if (name === "JSON") {
        const report = JSON.parse(artifact);
        expect(report.run_id).toBe(original.run_id);
        expect(report.model_mode).toBe("demo");
      } else expect(artifact).toContain("Mode: demo");
    }

    await page.locator('.main-nav a[href="/favorites"]').click();
    const savedPromise = waitForApi(page, /\/runs$/);
    await page.getByRole("button", { name: "Tải lại", exact: true }).click();
    const saved = await (await savedPromise).json();
    expect(
      saved.items.some((item: RunView) => item.run_id === original.run_id),
    ).toBe(true);
    await page
      .locator(`.saved-list a[href="/chat/runs/${original.run_id}"]`)
      .click();
    await finishRun(page, original.run_id);

    const retryPromise = waitForApi(
      page,
      `/runs/${original.run_id}/retry`,
      "POST",
      202,
    );
    await page.getByRole("button", { name: "Retry toàn bộ" }).click();
    const retried: RunView = await (await retryPromise).json();
    expect(retried.run_id).not.toBe(original.run_id);
    expect(retried.parent_run_id).toBe(original.run_id);
    expect(retried.run_kind).toBe("full");
    await finishRun(page, retried.run_id);

    await navigateInApp(page, `/chat/runs/${original.run_id}`);
    await finishRun(page, original.run_id);
    const reviewPromise = waitForApi(
      page,
      `/runs/${original.run_id}/review`,
      "POST",
      202,
    );
    await page
      .getByRole("button", { name: "Judge-only review", exact: true })
      .click();
    const reviewed: RunView = await (await reviewPromise).json();
    expect(reviewed.run_id).not.toBe(original.run_id);
    expect(reviewed.parent_run_id).toBe(original.run_id);
    expect(reviewed.run_kind).toBe("review");
    await finishRun(page, reviewed.run_id);
    await expect(
      page.getByText("Judge-only review đã tái sử dụng artifact", {
        exact: true,
      }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Mở hồ sơ" }).click();
    await expect(page.getByText("Bearer owner scope")).toBeVisible();
    const revokePromise = waitForApi(page, "/sessions/me", "DELETE", 204);
    await page.getByRole("button", { name: "Thu hồi và đăng xuất" }).click();
    await revokePromise;
    guest.revoked = true;
    guest.token = "";
    await expect(page).toHaveURL(/\/login$/);
  } finally {
    await revokeSession(page, guest);
  }
});

test("@api uploaded image is owner-scoped and reload discards browser credentials", async ({
  page,
  browser,
}) => {
  test.setTimeout(60_000);
  const guest = await guestLogin(page);
  let otherGuest: GuestSession | undefined;
  const otherContext = await browser.newContext({
    baseURL: new URL(page.url()).origin,
  });
  const otherPage = await otherContext.newPage();
  try {
    const imagePath = fileURLToPath(
      new URL("../../public/demo-thap-rua.jpg", import.meta.url),
    );
    await page.locator('input[type="file"]').setInputFiles(imagePath);
    await page
      .getByLabel("Câu hỏi")
      .fill("Mô tả các chi tiết kiến trúc nhìn thấy trong ảnh.");
    const uploadPromise = waitForApi(page, /\/assets$/, "POST", 201);
    const runPromise = waitForApi(page, /\/runs$/, "POST", 202);
    await page.getByRole("button", { name: "Tạo run" }).click();
    const asset = await (await uploadPromise).json();
    expect(asset.width).toBeGreaterThan(0);
    expect(asset.height).toBeGreaterThan(0);
    expect(asset.media_type).toBe("image/png");
    const run: RunView = await (await runPromise).json();
    expect(run.asset_id).toBe(asset.asset_id);
    await finishRun(page, run.run_id);
    const publicImageUrl = new URL(
      `/api/v1/assets/${asset.asset_id}/content`,
      guest.sessionsUrl,
    ).href;
    expect((await page.request.get(publicImageUrl)).status()).toBe(401);

    otherGuest = await guestLogin(otherPage);
    const hiddenPromise = waitForApi(
      otherPage,
      `/runs/${run.run_id}`,
      "GET",
      404,
    );
    await navigateInApp(otherPage, `/chat/runs/${run.run_id}`);
    await hiddenPromise;
    await expect(
      otherPage.getByText("Không tải được run", { exact: true }),
    ).toBeVisible();

    await page.reload();
    await expect(
      page.getByText("Phiên không còn trong bộ nhớ", { exact: true }),
    ).toBeVisible();
    const storage = await page.evaluate(() => ({
      local: Object.keys(localStorage),
      session: Object.keys(sessionStorage),
    }));
    expect(
      storage.local.some((key) => /token|credential|password/i.test(key)),
    ).toBe(false);
    expect(
      storage.session.some((key) => /token|credential|password/i.test(key)),
    ).toBe(false);
  } finally {
    await revokeSession(page, guest);
    if (otherGuest) await revokeSession(otherPage, otherGuest);
    await otherContext.close();
  }
});
