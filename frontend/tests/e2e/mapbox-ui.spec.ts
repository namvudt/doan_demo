import { expect, test, type Page } from "@playwright/test";

// Mapbox is intercepted before any request can leave the browser. The server
// config must use pk.fixture, never a developer's local access token.
const TILE = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=",
  "base64",
);

type Traffic = {
  documents: number;
  tilePaths: string[];
  errors: string[];
  forbidden: boolean;
};

async function isolatedMapbox(page: Page, forbidden = false) {
  const traffic: Traffic = {
    documents: 0,
    tilePaths: [],
    errors: [],
    forbidden,
  };
  page.on("request", (request) => {
    if (request.resourceType() === "document") traffic.documents += 1;
  });
  page.on("pageerror", (error) => traffic.errors.push(error.message));
  await page.route(/^https?:\/\//, async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname === "api.mapbox.com") {
      // A failed isolation assertion must not print an accidentally inherited
      // real token into the Playwright report.
      expect(
        url.searchParams.get("access_token") === "pk.fixture",
        "Only the fixture token may be used by this suite",
      ).toBe(true);
      expect(url.pathname).toMatch(
        /^\/styles\/v1\/mapbox\/streets-v12\/tiles\/512\/\d+\/\d+\/\d+$/,
      );
      traffic.tilePaths.push(url.pathname);
      await route.fulfill({
        status: traffic.forbidden ? 403 : 200,
        contentType: traffic.forbidden ? "text/plain" : "image/png",
        body: traffic.forbidden ? "Forbidden fixture" : TILE,
      });
    } else if (["127.0.0.1", "localhost"].includes(url.hostname)) {
      await route.continue();
    } else {
      await route.abort("blockedbyclient");
    }
  });
  return traffic;
}

async function settleMap(page: Page) {
  await expect(page.locator(".map-experience")).toHaveAttribute(
    "data-map-provider",
    "mapbox",
  );
  await expect(page.locator(".map-experience")).toHaveAttribute(
    "data-map-mode",
    "online",
  );
  await expect(page.locator(".leaflet-tile-loaded").first()).toBeVisible();
  await page.waitForFunction(async () => {
    let previous = "";
    let stableFrames = 0;
    for (let frame = 0; frame < 240; frame += 1) {
      const pane = document.querySelector<HTMLElement>(".leaflet-map-pane");
      const images = Array.from(
        document.querySelectorAll<HTMLImageElement>(".leaflet-tile"),
      );
      const bounds = document
        .querySelector(".leaflet-container")
        ?.getBoundingClientRect();
      const transforms = Array.from(
        document.querySelectorAll<HTMLElement>(
          ".leaflet-tile-container, .heritage-pin",
        ),
      ).map((element) => element.style.transform);
      const signature = `${pane?.style.transform}|${bounds?.width},${bounds?.height}|${transforms.join("|")}|${images
        .map((image) => `${image.src}:${image.style.opacity}`)
        .sort()
        .join("|")}`;
      const decoded =
        images.length > 0 &&
        images.every(
          (image) =>
            image.complete &&
            image.naturalWidth > 0 &&
            (!image.style.opacity || Number(image.style.opacity) >= 1),
        );
      stableFrames = decoded && signature === previous ? stableFrames + 1 : 0;
      if (stableFrames >= 8) return true;
      previous = signature;
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => resolve()),
      );
    }
    return false;
  });
}

async function tileZoom(page: Page) {
  return page.evaluate(() => {
    // Cached tiles at older zooms may remain in DOM during fade/pruning.
    const levels = Array.from(
      document.querySelectorAll<HTMLElement>(".leaflet-tile-container"),
    )
      .map((level) => {
        const transform = getComputedStyle(level).transform;
        const matrix = new DOMMatrixReadOnly(
          transform === "none" ? undefined : transform,
        );
        return { level, distance: Math.abs(matrix.a - 1) };
      })
      .sort((first, second) => first.distance - second.distance);
    const tile =
      levels[0]?.level.querySelector<HTMLImageElement>(".leaflet-tile");
    if (!tile) return null;
    const segments = new URL(tile.src).pathname.split("/");
    return Number(segments[segments.indexOf("512") + 1]);
  });
}

async function markerPosition(page: Page) {
  return page.evaluate(() => {
    const canvas = document
      .querySelector(".leaflet-container")!
      .getBoundingClientRect();
    const marker = document
      .querySelector(".heritage-pin")!
      .getBoundingClientRect();
    return {
      x: marker.x - canvas.x - canvas.width / 2,
      y: marker.y - canvas.y - canvas.height / 2,
    };
  });
}

async function checkCredits(page: Page) {
  const logo = page.locator(".map-provider-logo");
  await expect(logo).toBeVisible();
  await expect(logo).toHaveAttribute(
    "href",
    "https://www.mapbox.com/about/maps/",
  );
  await expect(logo.getByRole("img", { name: "Mapbox" })).toBeVisible();
  await expect
    .poll(() =>
      logo
        .locator("img")
        .evaluate((element) =>
          Boolean((element as HTMLImageElement).naturalWidth),
        ),
    )
    .toBe(true);
  const credit = page.locator(".leaflet-control-attribution");
  await expect(
    credit.getByRole("link", { name: "© Mapbox", exact: true }),
  ).toHaveAttribute("href", "https://www.mapbox.com/about/maps/");
  await expect(
    credit.getByRole("link", { name: "OpenStreetMap", exact: true }),
  ).toHaveAttribute("href", "https://www.openstreetmap.org/copyright");
  await expect(
    credit.getByRole("link", { name: "Improve this map", exact: true }),
  ).toHaveAttribute("href", "https://apps.mapbox.com/feedback/");
}

test("Mapbox uses native 512px tiles with the correct zoom offset and retained map", async ({
  page,
}) => {
  const traffic = await isolatedMapbox(page);
  await page.goto("/map?selected=preview-heritage-thap-rua");
  await settleMap(page);
  await checkCredits(page);
  // The selected-place camera is zoom 14. Native 512px tiles use URL zoom 13.
  expect(await tileZoom(page)).toBe(13);
  await expect(page.locator(".leaflet-tile").first()).toHaveCSS(
    "width",
    "512px",
  );
  await expect(page.locator(".leaflet-tile").first()).toHaveCSS(
    "height",
    "512px",
  );
  const pane = await page.locator(".leaflet-map-pane").elementHandle();
  const layer = await page
    .locator(".leaflet-tile-pane > .leaflet-layer")
    .elementHandle();
  const before = await markerPosition(page);
  const bounds = await page.locator(".leaflet-container").boundingBox();
  expect(bounds).not.toBeNull();
  await page.mouse.move(bounds!.x + bounds!.width * 0.6, bounds!.y + 160);
  await page.mouse.down();
  await page.mouse.move(
    bounds!.x + bounds!.width * 0.6 - 150,
    bounds!.y + 210,
    {
      steps: 14,
    },
  );
  await page.mouse.up();
  await settleMap(page);
  const moved = await markerPosition(page);
  expect(Math.hypot(moved.x - before.x, moved.y - before.y)).toBeGreaterThan(
    40,
  );
  await page.getByRole("button", { name: "Phóng to", exact: true }).click();
  await settleMap(page);
  expect(await tileZoom(page)).toBe(14);
  expect(await pane!.evaluate((element) => element.isConnected)).toBe(true);
  expect(await layer!.evaluate((element) => element.isConnected)).toBe(true);
  await expect(page.locator(".map-leaflet-canvas")).toHaveClass(
    /leaflet-container/,
  );
  expect(traffic.documents).toBe(1);
  expect(traffic.tilePaths.length).toBeGreaterThan(0);
  expect(traffic.errors).toEqual([]);
});

test("Mapbox HTTP 403 fallback can retry without losing camera or native Leaflet classes", async ({
  page,
}) => {
  const traffic = await isolatedMapbox(page, true);
  await page.goto("/map?selected=preview-heritage-thap-rua");
  await expect(page.getByTestId("offline-map")).toBeVisible();
  await expect(page.locator(".heritage-pin").first()).toBeAttached();
  await expect(page.locator(".map-provider-logo")).toHaveCount(0);
  const pane = await page.locator(".leaflet-map-pane").elementHandle();
  const markers = await page.locator(".heritage-pin").elementHandles();
  const before = await markerPosition(page);
  traffic.forbidden = false;
  await page
    .getByRole("button", { name: "Thử tải bản đồ", exact: true })
    .click();
  await settleMap(page);
  await checkCredits(page);
  const recovered = await markerPosition(page);
  expect(Math.abs(recovered.x - before.x)).toBeLessThanOrEqual(2);
  expect(Math.abs(recovered.y - before.y)).toBeLessThanOrEqual(2);
  expect(await tileZoom(page)).toBe(13);
  for (const marker of markers) {
    expect(await marker.evaluate((element) => element.isConnected)).toBe(true);
  }
  const requests = traffic.tilePaths.length;
  await page.getByRole("button", { name: "Xem sơ đồ", exact: true }).click();
  await expect(page.getByTestId("offline-map")).toBeVisible();
  await expect(page.locator(".map-provider-logo")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Quay lại bản đồ", exact: true })
    .click();
  await settleMap(page);
  await checkCredits(page);
  expect(traffic.tilePaths).toHaveLength(requests);
  expect(await pane!.evaluate((element) => element.isConnected)).toBe(true);
  await expect(page.locator(".map-leaflet-canvas")).toHaveClass(
    /leaflet-container/,
  );
  expect(traffic.documents).toBe(1);
  expect(traffic.errors).toEqual([]);
});

test("@mobile Mapbox logo and attribution remain visible without covering each other", async ({
  page,
}) => {
  const traffic = await isolatedMapbox(page);
  await page.goto("/map");
  for (const viewport of [
    { width: 390, height: 844 },
    { width: 320, height: 600 },
  ]) {
    await page.setViewportSize(viewport);
    await settleMap(page);
    await checkCredits(page);
    const surface = await page.locator(".map-surface").boundingBox();
    const logo = await page.locator(".map-provider-logo").boundingBox();
    const credit = await page
      .locator(".leaflet-control-attribution")
      .boundingBox();
    expect(surface).not.toBeNull();
    expect(logo).not.toBeNull();
    expect(credit).not.toBeNull();
    for (const box of [logo!, credit!]) {
      expect(box.x).toBeGreaterThanOrEqual(surface!.x - 1);
      expect(box.y).toBeGreaterThanOrEqual(surface!.y - 1);
      expect(box.x + box.width).toBeLessThanOrEqual(
        surface!.x + surface!.width + 1,
      );
      expect(box.y + box.height).toBeLessThanOrEqual(
        surface!.y + surface!.height + 1,
      );
    }
    const overlapWidth = Math.max(
      0,
      Math.min(logo!.x + logo!.width, credit!.x + credit!.width) -
        Math.max(logo!.x, credit!.x),
    );
    const overlapHeight = Math.max(
      0,
      Math.min(logo!.y + logo!.height, credit!.y + credit!.height) -
        Math.max(logo!.y, credit!.y),
    );
    expect(overlapWidth * overlapHeight).toBe(0);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  expect(traffic.documents).toBe(1);
  expect(traffic.errors).toEqual([]);
});
