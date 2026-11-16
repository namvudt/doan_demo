import { expect, test, type Page } from "@playwright/test";

test.skip(
  process.env.RUN_CATALOG_API !== "1",
  "Run explicitly against the deployed local catalog API.",
);

type HeritageRecord = {
  heritage_id: string;
  name: string;
  province: string;
  content_status: string;
  illustrative: boolean;
  location: {
    latitude: number;
    longitude: number;
    verification_status: string;
  } | null;
  media: Array<{ media_id: string; url: string; alt: string }>;
};

type CatalogPage = { items: HeritageRecord[]; total: number };

async function deployedCatalog(page: Page) {
  const capabilities = await page.request.get("/api/v1/capabilities");
  expect(capabilities.ok()).toBe(true);
  const caps = await capabilities.json();
  expect(caps.features?.heritage_catalog).toBe(true);
  const response = await page.request.get("/api/v1/heritages?limit=100");
  expect(response.ok()).toBe(true);
  const catalog = (await response.json()) as CatalogPage;
  expect(catalog.total).toBeGreaterThanOrEqual(7);
  expect(
    catalog.items.every((item) => item.content_status === "published"),
  ).toBe(true);
  return catalog;
}

test.beforeEach(async ({ page }) => {
  // Only local API/media traffic is needed. No map-provider or model request.
  await page.route(/^https?:\/\//, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (!["127.0.0.1", "localhost"].includes(url.hostname)) {
      await route.abort("blockedbyclient");
    } else if (url.pathname === "/api/v1/runs" && request.method() === "POST") {
      await route.abort("blockedbyclient");
    } else {
      await route.continue();
    }
  });
});

test("persisted API catalog, detail media and map share the same heritage identity", async ({
  page,
}) => {
  const errors: string[] = [];
  const catalogReads: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (path.startsWith("/api/v1/heritages")) catalogReads.push(path);
  });
  const catalog = await deployedCatalog(page);
  const selected = catalog.items.find((item) => item.name.includes("Văn Miếu"));
  expect(selected).toBeTruthy();
  expect(selected!.location?.verification_status).toBe("illustrative");

  await page.goto("/heritages");
  await expect(page.locator(".heritage-card")).toHaveCount(
    catalog.items.length,
  );
  await expect(page.locator(".preview-banner")).toHaveCount(0);
  await expect(
    page.getByText("Dữ liệu backend", { exact: true }).first(),
  ).toBeVisible();
  const catalogImages = page.locator(".heritage-card img");
  await expect(catalogImages).toHaveCount(catalog.items.length);
  for (let index = 0; index < catalog.items.length; index += 1) {
    const image = catalogImages.nth(index);
    await image.scrollIntoViewIfNeeded();
    await expect
      .poll(() =>
        image.evaluate((node) => (node as HTMLImageElement).naturalWidth),
      )
      .toBeGreaterThan(0);
    await image.evaluate((node) => (node as HTMLImageElement).decode());
    await expect(image).toBeVisible();
    await expect
      .poll(() =>
        image.evaluate((node) =>
          Number.parseFloat(getComputedStyle(node).opacity),
        ),
      )
      .toBeGreaterThanOrEqual(0.9);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "artifacts/screenshots/catalog-api/catalog-desktop.png",
    fullPage: true,
  });
  await page
    .getByRole("textbox", { name: "Tìm di sản", exact: true })
    .fill("Văn Miếu");
  await expect(page.locator(".heritage-card")).toHaveCount(1);
  await page
    .getByRole("heading", { name: selected!.name, exact: true })
    .click();
  await expect
    .poll(() => new URL(page.url()).pathname)
    .toBe(`/heritages/${selected!.heritage_id}`);
  await expect(
    page.getByRole("heading", { name: selected!.name, level: 1 }),
  ).toBeVisible();
  const image = page.locator(".detail-image img").first();
  await expect(image).toBeVisible();
  await expect
    .poll(() =>
      image.evaluate((node) => {
        const element = node as HTMLImageElement;
        return element.complete && element.naturalWidth > 0;
      }),
    )
    .toBe(true);
  expect(
    await image.evaluate(
      (node) => new URL((node as HTMLImageElement).currentSrc).pathname,
    ),
  ).toContain(`/api/v1/heritages/${selected!.heritage_id}/media/`);
  await expect(page.locator("main")).toContainText(/minh họa/i);

  await page
    .getByRole("button", { name: "Mở trên bản đồ", exact: true })
    .click();
  await expect
    .poll(() => new URL(page.url()).searchParams.get("selected"))
    .toBe(selected!.heritage_id);
  await expect(
    page
      .locator(".map-preview-card")
      .getByRole("heading", { name: selected!.name }),
  ).toBeVisible();
  await expect(
    page
      .locator(".map-results")
      .getByRole("button", { name: new RegExp(selected!.name) }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("offline-map")).toBeVisible();
  await expect(page.locator(".preview-banner")).toHaveCount(0);
  await page.screenshot({
    path: "artifacts/screenshots/catalog-api/map-selected-desktop.png",
    fullPage: true,
  });
  expect(catalogReads.length).toBeGreaterThanOrEqual(3);
  expect(errors).toEqual([]);
});

test("API catalog filtering and reload use persisted records without Preview storage", async ({
  page,
}) => {
  const catalog = await deployedCatalog(page);
  await page.goto("/heritages");
  await expect(page.locator(".heritage-card")).toHaveCount(
    catalog.items.length,
  );
  await page
    .getByRole("combobox", { name: "Địa phương", exact: true })
    .selectOption("Hà Nội");
  const expected = catalog.items.filter((item) => item.province === "Hà Nội");
  await expect(page.locator(".heritage-card")).toHaveCount(expected.length);
  const namesBefore = await page.locator(".heritage-card h2").allTextContents();
  await page.reload();
  await expect(page.locator(".heritage-card")).toHaveCount(expected.length);
  expect(await page.locator(".heritage-card h2").allTextContents()).toEqual(
    namesBefore,
  );
  await expect(page.locator(".preview-banner")).toHaveCount(0);

  await page
    .getByRole("textbox", { name: "Tìm di sản", exact: true })
    .fill("không có di tích thử nghiệm xyz");
  await expect(page.locator(".heritage-card")).toHaveCount(0);
  await expect(
    page.getByText("Không có kết quả phù hợp", { exact: true }),
  ).toBeVisible();
  const response = await page.request.get("/api/v1/heritages?limit=100");
  expect(((await response.json()) as CatalogPage).total).toBe(catalog.total);
});

test("a catalog photo enters the guest composer without submitting an AI run", async ({
  page,
}) => {
  const catalog = await deployedCatalog(page);
  const selected = catalog.items.find((item) => item.name.includes("Văn Miếu"));
  expect(selected).toBeTruthy();
  const capabilities = await (
    await page.request.get("/api/v1/capabilities")
  ).json();
  expect(capabilities.features?.heritage_asset_import).toBe(true);
  expect(capabilities.session_bootstrap_required).toBe(false);
  let token = "";
  let sessionsUrl = "";
  const runsCreated: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/v1/runs"
    ) {
      runsCreated.push("POST /api/v1/runs");
    }
  });

  try {
    await page.goto(`/heritages/${selected!.heritage_id}`);
    await page
      .getByRole("button", { name: "Hỏi về di sản", exact: true })
      .click();
    await expect
      .poll(() => new URL(page.url()).searchParams.get("heritage"))
      .toBe(selected!.heritage_id);
    await page
      .locator("main")
      .getByRole("link", { name: "Truy cập phiên khách", exact: true })
      .click();
    const sessionResponse = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === "/api/v1/sessions" &&
        response.request().method() === "POST" &&
        response.status() === 201,
    );
    const imageImported = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname ===
          `/api/v1/heritages/${selected!.heritage_id}/media/${selected!.media[0]!.media_id}/assets` &&
        response.request().method() === "POST" &&
        response.status() === 201,
    );
    await page
      .getByRole("button", { name: "Tạo phiên khách", exact: true })
      .click();
    const response = await sessionResponse;
    token = ((await response.json()) as { access_token: string }).access_token;
    sessionsUrl = response.url();
    await imageImported;
    await expect(
      page.getByText("Đã chọn ảnh từ hồ sơ di sản", { exact: true }),
    ).toBeVisible();
    await expect(page.locator(".ai-attachment-select")).toContainText(
      selected!.name,
    );
    const attachment = page.locator(".ai-attachment-preview img");
    await expect(attachment).toBeVisible();
    await expect
      .poll(() =>
        attachment.evaluate((node) => (node as HTMLImageElement).naturalWidth),
      )
      .toBeGreaterThan(0);
    await page
      .getByRole("button", { name: "Bỏ ảnh đã chọn", exact: true })
      .click();
    await expect(page.locator(".ai-attachment-preview")).toHaveCount(0);
    expect(runsCreated).toEqual([]);
    const runs = await page.request.get("/api/v1/runs", {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(((await runs.json()) as { total: number }).total).toBe(0);
  } finally {
    if (token && sessionsUrl) {
      await page.request.delete(`${sessionsUrl}/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
    }
  }
});
