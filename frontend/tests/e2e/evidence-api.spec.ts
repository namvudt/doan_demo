import { mkdir } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import type { ResultView, RunView } from "../../src/api/schema";

test.skip(
  process.env.RUN_EVIDENCE_API !== "1",
  "Run explicitly against the deployed local demo evidence backend.",
);
test.use({ trace: "off" });

type Guest = { token: string; sessionsUrl: string };

async function signIn(page: Page): Promise<Guest> {
  const response = await page.request.get("/api/v1/capabilities");
  expect(response.ok()).toBe(true);
  const capabilities = await response.json();
  expect(capabilities.model_mode).toBe("demo");
  expect(capabilities.accuracy?.enabled).toBe(true);
  expect(capabilities.features?.heritage_catalog).toBe(true);
  expect(response.headers()["x-backend-build"]).toBeTruthy();
  expect(capabilities.session_bootstrap_required).toBe(false);
  await page.goto("/login");
  const created = page.waitForResponse(
    (item) =>
      new URL(item.url()).pathname === "/api/v1/sessions" &&
      item.request().method() === "POST" &&
      item.status() === 201,
  );
  await page
    .getByRole("button", { name: "Tạo phiên khách", exact: true })
    .click();
  const session = await created;
  const body = (await session.json()) as { access_token: string };
  await expect(page).toHaveURL(/\/chat$/);
  return { token: body.access_token, sessionsUrl: session.url() };
}

async function signOut(page: Page, guest: Guest) {
  await page.request.delete(`${guest.sessionsUrl}/me`, {
    headers: { Authorization: `Bearer ${guest.token}` },
  });
  guest.token = "";
}

async function navigate(page: Page, pathname: string) {
  await page.evaluate((path) => {
    window.history.pushState(null, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, pathname);
}

async function createEvidenceRun(page: Page, guest: Guest) {
  const headers = { Authorization: `Bearer ${guest.token}` };
  const samples = (await (
    await page.request.get("/api/v1/samples", { headers })
  ).json()) as {
    items: Array<{ sample_id: string }>;
  };
  expect(samples.items.length).toBeGreaterThan(0);
  const assetResponse = await page.request.post(
    `/api/v1/samples/${samples.items[0]!.sample_id}/assets`,
    { headers },
  );
  expect(assetResponse.status()).toBe(201);
  const asset = (await assetResponse.json()) as { asset_id: string };
  const created = await page.request.post("/api/v1/runs", {
    headers: {
      ...headers,
      "Idempotency-Key": `evidence-ui-${crypto.randomUUID()}`,
    },
    data: {
      asset_id: asset.asset_id,
      question: "Mô tả chi tiết nhìn thấy và đối chiếu tư liệu của công trình.",
      focus_box: [0.1, 0.1, 0.8, 0.8],
      location_hint: { name: "Gợi ý thử nghiệm UI", provenance: "user" },
    },
  });
  expect(created.status()).toBe(202);
  const queued = (await created.json()) as RunView;
  let run = queued;
  await expect
    .poll(
      async () => {
        run = (await (
          await page.request.get(`/api/v1/runs/${queued.run_id}`, { headers })
        ).json()) as RunView;
        return ["succeeded", "awaiting_input"].includes(run.execution_status);
      },
      { timeout: 20_000 },
    )
    .toBe(true);
  const resultResponse = await page.request.get(
    `/api/v1/runs/${run.run_id}/result`,
    {
      headers,
    },
  );
  expect(resultResponse.ok()).toBe(true);
  const result = (await resultResponse.json()) as ResultView;
  expect(result.result_schema_version).toBe(2);
  return { run, result };
}

test.beforeEach(async ({ page }) => {
  await page.route(/^https?:\/\//, async (route) => {
    const host = new URL(route.request().url()).hostname;
    if (["127.0.0.1", "localhost"].includes(host)) await route.continue();
    else await route.abort("blockedbyclient");
  });
});

test("real Docker evidence result, recognition and authenticated region crop render in React", async ({
  page,
}) => {
  test.setTimeout(60_000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const guest = await signIn(page);
  try {
    const { run, result } = await createEvidenceRun(page, guest);
    const headers = { Authorization: `Bearer ${guest.token}` };
    const evidence = await page.request.get(
      `/api/v1/runs/${run.run_id}/evidence`,
      { headers },
    );
    expect(evidence.ok()).toBe(true);
    expect((await evidence.json()).recognition).toEqual(result.recognition);
    await navigate(page, `/chat/runs/${run.run_id}`);
    const panel = page.getByRole("region", {
      name: "Nhận diện và bằng chứng",
      exact: true,
    });
    await expect(panel).toBeVisible();
    await expect(page.getByTestId("recognition-result")).toBeVisible();
    await expect(panel).toContainText("Đánh giá tự động");
    await expect(panel).toContainText("Gợi ý thử nghiệm UI");
    await expect(panel).toContainText("Đây không phải bằng chứng đã xác minh");
    await expect(page.getByTestId("evidence-claims")).toBeVisible();
    await panel.getByText(/^Bằng chứng đã thu thập \(/).click();
    await expect(panel).toContainText("DEMO");
    expect(result.regions?.length).toBeGreaterThan(0);
    await panel.getByText(/^Vùng ảnh đã xử lý \(/).click();
    const cropResponse = page.waitForResponse(
      (response) =>
        /\/regions\/[^/]+\/image$/.test(new URL(response.url()).pathname) &&
        response.status() === 200,
    );
    await panel.getByText("Xem vùng ảnh", { exact: true }).first().click();
    expect((await cropResponse).headers()["content-type"]).toContain(
      "image/png",
    );
    const crop = panel.locator("img").first();
    await expect(crop).toBeVisible();
    await expect
      .poll(() =>
        crop.evaluate((node) => (node as HTMLImageElement).naturalWidth),
      )
      .toBeGreaterThan(0);
    await expect(
      page.getByRole("button", { name: /Yêu cầu hủy|Đang yêu cầu hủy/ }),
    ).toHaveCount(0);
    expect(errors).toEqual([]);
    const dismiss = page.getByRole("button", {
      name: "Đóng thông báo",
      exact: true,
    });
    while (await dismiss.count()) await dismiss.first().click();
    await page.getByRole("heading", { name: run.question, level: 1 }).click();
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
    await expect(page.locator(".toast")).toHaveCount(0);
    await mkdir("artifacts/screenshots/evidence-api", { recursive: true });
    await page.screenshot({
      path: "artifacts/screenshots/evidence-api/real-demo-evidence.png",
      fullPage: true,
    });
  } finally {
    await signOut(page, guest);
  }
});

test("labelled UI fixture: pending clarification stops streaming and submits an explicit idempotent child request", async ({
  page,
}) => {
  test.setTimeout(60_000);
  const guest = await signIn(page);
  try {
    // Real owned assets/runs/results remain the baseline. Only this pending
    // response is simulated: the default demo model normally answers directly.
    const parent = await createEvidenceRun(page, guest);
    const child = await createEvidenceRun(page, guest);
    const base = `/api/v1/runs/${parent.run.run_id}`;
    const pending = {
      clarification_id: "ui-pending-fixture",
      revision: 1,
      reason: "entity_ambiguous",
      question: "Tình huống UI mô phỏng: bạn muốn đối chiếu địa điểm nào?",
      options: ["DEMO", "OTHER"],
      rounds: 0,
    };
    let submissions = 0;
    let runReads = 0;
    let streams = 0;
    await page.route(`**${base}`, async (route) => {
      runReads += 1;
      await route.fulfill({
        json: {
          ...parent.run,
          execution_status: "awaiting_input",
          result_status: "needs_clarification",
        },
      });
    });
    await page.route(`**${base}/result`, async (route) => {
      await route.fulfill({
        json: {
          ...parent.result,
          answer_status: "needs_clarification",
          clarification: pending,
        },
      });
    });
    await page.route(`**${base}/clarification`, async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          json: {
            run_id: parent.run.run_id,
            execution_status: "awaiting_input",
            clarification: pending,
            continuation_run_id: null,
          },
        });
      } else {
        submissions += 1;
        const body = route.request().postDataJSON() as Record<string, unknown>;
        expect(body).toMatchObject({
          clarification_id: pending.clarification_id,
          revision: 1,
          selected_candidate: "DEMO",
          answer: "Thông tin UI thử nghiệm",
        });
        expect(route.request().headers()["idempotency-key"]).toBeTruthy();
        await route.fulfill({
          status: 202,
          json: {
            ...child.run,
            run_kind: "clarification",
            parent_run_id: parent.run.run_id,
          },
        });
      }
    });
    page.on("request", (request) => {
      if (new URL(request.url()).pathname === `${base}/events`) streams += 1;
    });
    await navigate(page, `/chat/runs/${parent.run.run_id}`);
    const panel = page.getByTestId("clarification-panel");
    await expect(panel).toBeVisible();
    await expect(panel).toContainText("Tình huống UI mô phỏng");
    await expect(
      panel.getByRole("button", { name: "Gửi thông tin bổ sung", exact: true }),
    ).toBeDisabled();
    await expect(
      page.getByRole("button", { name: /Yêu cầu hủy|Đang yêu cầu hủy/ }),
    ).toHaveCount(0);
    const readsBeforeInput = runReads;
    await panel
      .getByRole("combobox", { name: "Địa điểm bạn muốn đối chiếu" })
      .selectOption("DEMO");
    await panel
      .getByRole("textbox", { name: "Thông tin bổ sung" })
      .fill("Thông tin UI thử nghiệm");
    // Give an accidentally reopened poll/stream enough time to become visible.
    await page.waitForTimeout(1200);
    expect(submissions).toBe(0);
    expect(streams).toBe(0);
    expect(runReads).toBe(readsBeforeInput);
    await mkdir("artifacts/screenshots/evidence-api", { recursive: true });
    await page.screenshot({
      path: "artifacts/screenshots/evidence-api/pending-clarification-ui-fixture.png",
      fullPage: true,
    });
    await panel
      .getByRole("button", { name: "Gửi thông tin bổ sung", exact: true })
      .click();
    await expect(page).toHaveURL(new RegExp(`/chat/runs/${child.run.run_id}$`));
    expect(submissions).toBe(1);
    await expect(
      page.getByRole("region", {
        name: "Nhận diện và bằng chứng",
        exact: true,
      }),
    ).toBeVisible();
  } finally {
    await signOut(page, guest);
  }
});
