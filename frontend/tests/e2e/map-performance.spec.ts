import { expect, test, type ElementHandle, type Page } from "@playwright/test";

// A valid local fixture makes network/render lifecycle checks deterministic.
// No map-provider or model request leaves the browser during this suite.
const TILE = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=",
  "base64",
);

type Traffic = {
  documents: string[];
  tiles: string[];
  errors: string[];
  failTiles: boolean;
};

async function installControlledTiles(
  page: Page,
  failTiles = false,
): Promise<Traffic> {
  const traffic: Traffic = { documents: [], tiles: [], errors: [], failTiles };
  page.on("request", (request) => {
    if (request.resourceType() === "document") {
      traffic.documents.push(request.url());
    }
    if (new URL(request.url()).hostname === "tiles.test") {
      traffic.tiles.push(request.url());
    }
  });
  page.on("pageerror", (error) => traffic.errors.push(error.message));
  await page.route(/^https?:\/\//, async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname === "tiles.test") {
      if (traffic.failTiles) await route.abort("failed");
      else await route.fulfill({ contentType: "image/png", body: TILE });
    } else if (url.hostname === "127.0.0.1" || url.hostname === "localhost") {
      await route.continue();
    } else {
      await route.abort("blockedbyclient");
    }
  });
  return traffic;
}

async function settleMap(page: Page) {
  await expect(page.locator(".map-canvas")).toHaveAttribute(
    "data-map-mode",
    "online",
  );
  await expect(page.locator(".leaflet-tile-loaded").first()).toBeVisible();
  // Synchronize with actual Leaflet movement and decoded tiles. This is not a
  // machine-dependent elapsed-time performance assertion.
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
      ).map((node) => node.style.transform);
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

async function openMap(page: Page, path = "/map") {
  await page.goto(path);
  await settleMap(page);
}

async function retained(
  page: Page,
  handle: ElementHandle<HTMLElement | SVGElement> | null,
  selector: string,
) {
  expect(handle).not.toBeNull();
  expect(
    await handle!.evaluate(
      (node, expectedSelector) =>
        node.isConnected && node === document.querySelector(expectedSelector),
      selector,
    ),
  ).toBe(true);
  await expect(page.locator(selector)).toHaveCount(1);
}

async function dragMap(page: Page) {
  const bounds = await page.locator(".leaflet-container").boundingBox();
  expect(bounds).not.toBeNull();
  const start = {
    x: bounds!.x + bounds!.width * 0.61,
    y: bounds!.y + bounds!.height * 0.4,
  };
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(start.x - 160, start.y + 65, { steps: 14 });
  await page.mouse.up();
  await settleMap(page);
}

async function cameraSnapshot(page: Page) {
  return page.evaluate(() => {
    const canvas = document.querySelector(".leaflet-container")!;
    const marker = document.querySelector(".heritage-pin")!;
    const bounds = canvas.getBoundingClientRect();
    const point = marker.getBoundingClientRect();
    return {
      x: point.x - bounds.x - bounds.width / 2,
      y: point.y - bounds.y - bounds.height / 2,
      zoom: (() => {
        // Leaflet retains tiles from older zoom levels while fading/pruning.
        // The active level has scale 1; DOM insertion order is not camera state.
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
        return tile ? new URL(tile.src).pathname.split("/")[1] : null;
      })(),
    };
  });
}

test("dragging and zooming retain the map and avoid document reloads", async ({
  page,
}, testInfo) => {
  const traffic = await installControlledTiles(page);
  await openMap(page);
  const pane = await page.locator(".leaflet-map-pane").elementHandle();
  const layer = await page
    .locator(".leaflet-tile-pane > .leaflet-layer")
    .elementHandle();
  const before = await cameraSnapshot(page);

  await dragMap(page);
  const panned = await cameraSnapshot(page);
  expect(Math.hypot(panned.x - before.x, panned.y - before.y)).toBeGreaterThan(
    40,
  );
  await retained(page, pane, ".leaflet-map-pane");
  await retained(page, layer, ".leaflet-tile-pane > .leaflet-layer");

  await page.getByRole("button", { name: "Phóng to", exact: true }).click();
  await settleMap(page);
  expect((await cameraSnapshot(page)).zoom).not.toBe(panned.zoom);
  await page.getByRole("button", { name: "Thu nhỏ", exact: true }).click();
  await settleMap(page);
  await retained(page, pane, ".leaflet-map-pane");
  await retained(page, layer, ".leaflet-tile-pane > .leaflet-layer");
  expect(traffic.documents).toHaveLength(1);
  expect(traffic.errors).toEqual([]);
  expect(traffic.tiles.length).toBeGreaterThan(0);
  await testInfo.attach("map-request-counts", {
    body: JSON.stringify({
      documentRequests: traffic.documents.length,
      tileRequests: traffic.tiles.length,
      uniqueTileUrls: new Set(traffic.tiles).size,
    }),
    contentType: "application/json",
  });
});

test("selection keeps existing marker nodes and stable views keep their tiles", async ({
  page,
}) => {
  const traffic = await installControlledTiles(page);
  await openMap(page);
  const markers = await page.locator(".heritage-pin").elementHandles();
  expect(markers.length).toBeGreaterThan(1);
  await page
    .locator(".map-results")
    .getByRole("button", { name: /Đô thị cổ Hội An/ })
    .click();
  await settleMap(page);
  await expect(
    page.locator('.heritage-pin[title="Đô thị cổ Hội An"]'),
  ).toHaveAttribute("aria-pressed", "true");
  for (const marker of markers) {
    expect(await marker.evaluate((node) => node.isConnected)).toBe(true);
  }
  await expect(page.locator(".heritage-pin")).toHaveCount(markers.length);

  const tiles = await page.locator(".leaflet-tile").elementHandles();
  const requests = traffic.tiles.length;
  await page
    .locator(".map-results")
    .getByRole("button", { name: /Đô thị cổ Hội An/ })
    .click();
  await settleMap(page);
  expect(traffic.tiles).toHaveLength(requests);
  await expect(page.locator(".leaflet-tile")).toHaveCount(tiles.length);
  for (const tile of tiles) {
    expect(await tile.evaluate((node) => node.isConnected)).toBe(true);
  }
  expect(traffic.errors).toEqual([]);
});

test("list-only, collapsed panels and expanded map retain the camera", async ({
  page,
}) => {
  const traffic = await installControlledTiles(page);
  await openMap(page);
  await dragMap(page);
  await page.getByRole("button", { name: "Phóng to", exact: true }).click();
  await settleMap(page);
  const pane = await page.locator(".leaflet-map-pane").elementHandle();
  const initial = await cameraSnapshot(page);

  await page
    .getByRole("button", { name: "Mở rộng thông tin địa điểm" })
    .click();
  await settleMap(page);
  const withDetails = await cameraSnapshot(page);
  expect(withDetails.zoom).toBe(initial.zoom);
  expect(Math.abs(withDetails.x - initial.x)).toBeLessThanOrEqual(2);
  expect(Math.abs(withDetails.y - initial.y)).toBeLessThanOrEqual(2);
  await page
    .getByRole("button", { name: "Thu gọn thông tin địa điểm" })
    .click();
  await settleMap(page);
  await retained(page, pane, ".leaflet-map-pane");

  await page
    .getByRole("button", { name: "Chỉ danh sách", exact: true })
    .click();
  await expect(page.locator(".leaflet-container")).toBeHidden();
  await page.getByRole("button", { name: "Hiện bản đồ", exact: true }).click();
  await settleMap(page);
  await retained(page, pane, ".leaflet-map-pane");
  const restored = await cameraSnapshot(page);
  expect(restored.zoom).toBe(initial.zoom);
  expect(Math.abs(restored.x - initial.x)).toBeLessThanOrEqual(2);
  expect(Math.abs(restored.y - initial.y)).toBeLessThanOrEqual(2);

  await page
    .getByRole("button", { name: "Thu gọn danh sách", exact: true })
    .click();
  await settleMap(page);
  const withSidebarCollapsed = await cameraSnapshot(page);
  expect(withSidebarCollapsed.zoom).toBe(initial.zoom);
  expect(Math.abs(withSidebarCollapsed.x - initial.x)).toBeLessThanOrEqual(2);
  expect(Math.abs(withSidebarCollapsed.y - initial.y)).toBeLessThanOrEqual(2);
  await page.getByRole("button", { name: "Mở danh sách", exact: true }).click();
  await settleMap(page);
  await retained(page, pane, ".leaflet-map-pane");
  const afterSidebar = await cameraSnapshot(page);
  expect(afterSidebar.zoom).toBe(initial.zoom);
  expect(Math.abs(afterSidebar.x - initial.x)).toBeLessThanOrEqual(2);
  expect(Math.abs(afterSidebar.y - initial.y)).toBeLessThanOrEqual(2);

  await page
    .getByRole("button", { name: "Mở rộng bản đồ", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await settleMap(page);
  const expanded = await cameraSnapshot(page);
  expect(expanded.zoom).toBe(initial.zoom);
  expect(Math.abs(expanded.x - initial.x)).toBeLessThanOrEqual(2);
  expect(Math.abs(expanded.y - initial.y)).toBeLessThanOrEqual(2);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await settleMap(page);
  await retained(page, pane, ".leaflet-map-pane");
  const afterExpansion = await cameraSnapshot(page);
  expect(afterExpansion.zoom).toBe(initial.zoom);
  expect(Math.abs(afterExpansion.x - initial.x)).toBeLessThanOrEqual(2);
  expect(Math.abs(afterExpansion.y - initial.y)).toBeLessThanOrEqual(2);

  await page
    .getByRole("textbox", { name: "Tìm trên bản đồ" })
    .fill("không có di sản xyz");
  await expect(page.locator(".map-result")).toHaveCount(0);
  await retained(page, pane, ".leaflet-map-pane");
  await page.getByRole("textbox", { name: "Tìm trên bản đồ" }).fill("");
  await settleMap(page);
  await retained(page, pane, ".leaflet-map-pane");
  expect(traffic.documents).toHaveLength(1);
  expect(traffic.errors).toEqual([]);
});

test("failed tiles recover without resetting the camera and schematic keeps the healthy layer", async ({
  page,
}) => {
  const traffic = await installControlledTiles(page, true);
  await page.goto("/map?selected=preview-heritage-van-mieu");
  await expect(page.getByTestId("offline-map")).toBeVisible();
  await expect(page.locator(".heritage-pin").first()).toBeAttached();
  expect(traffic.tiles.length).toBeGreaterThan(0);
  const pane = await page.locator(".leaflet-map-pane").elementHandle();
  const markers = await page.locator(".heritage-pin").elementHandles();
  const before = await cameraSnapshot(page);
  traffic.failTiles = false;
  await page
    .getByRole("button", { name: "Thử tải bản đồ", exact: true })
    .click();
  await settleMap(page);
  await retained(page, pane, ".leaflet-map-pane");
  const recovered = await cameraSnapshot(page);
  expect(Math.abs(recovered.x - before.x)).toBeLessThanOrEqual(2);
  expect(Math.abs(recovered.y - before.y)).toBeLessThanOrEqual(2);
  for (const marker of markers) {
    expect(await marker.evaluate((node) => node.isConnected)).toBe(true);
  }

  await dragMap(page);
  const healthyCamera = await cameraSnapshot(page);
  const layer = await page
    .locator(".leaflet-tile-pane > .leaflet-layer")
    .elementHandle();
  const tiles = await page.locator(".leaflet-tile").elementHandles();
  const requests = traffic.tiles.length;
  await page.getByRole("button", { name: "Xem sơ đồ", exact: true }).click();
  await expect(page.getByTestId("offline-map")).toBeVisible();
  await page
    .getByRole("button", { name: "Quay lại bản đồ", exact: true })
    .click();
  await settleMap(page);
  await retained(page, pane, ".leaflet-map-pane");
  await retained(page, layer, ".leaflet-tile-pane > .leaflet-layer");
  expect(await cameraSnapshot(page)).toEqual(healthyCamera);
  expect(traffic.tiles).toHaveLength(requests);
  for (const tile of tiles) {
    expect(await tile.evaluate((node) => node.isConnected)).toBe(true);
  }
  expect(traffic.documents).toHaveLength(1);
  expect(traffic.errors).toEqual([]);
});

test("leaving during map movement disposes pending callbacks", async ({
  page,
}) => {
  const traffic = await installControlledTiles(page);
  for (let iteration = 0; iteration < 3; iteration += 1) {
    await openMap(page);
    await page.getByRole("button", { name: "Phóng to", exact: true }).click();
    await page
      .locator(".map-results")
      .getByRole("button", { name: /Đô thị cổ Hội An/ })
      .click();
    await page.locator('.main-nav a[href="/heritages"]').click();
    await expect(page.locator(".leaflet-container")).toHaveCount(0);
    await expect(page.locator(".heritage-grid")).toBeVisible();
  }
  // Observe beyond Leaflet's delayed zoom completion after the final unmount.
  await page.waitForTimeout(500);
  expect(traffic.errors).toEqual([]);
});

test("@mobile map panels and expanded map fit the viewport", async ({
  page,
}) => {
  const traffic = await installControlledTiles(page);
  await openMap(page);
  const pane = await page.locator(".leaflet-map-pane").elementHandle();
  await expect(
    page.getByRole("button", { name: "Mở danh sách", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Mở danh sách", exact: true }).click();
  await expect(page.locator(".map-results")).toBeVisible();
  await page
    .getByRole("button", { name: "Thu gọn danh sách", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Mở rộng bản đồ", exact: true })
    .click();
  await settleMap(page);
  await expect(page.getByRole("dialog")).toBeVisible();
  const bounds = await page.getByRole("dialog").boundingBox();
  const viewport = page.viewportSize()!;
  expect(bounds).not.toBeNull();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.y).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width + 1);
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(viewport.height + 1);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Thu gọn bản đồ", exact: true })
    .click();
  await settleMap(page);
  await retained(page, pane, ".leaflet-map-pane");
  expect(traffic.documents).toHaveLength(1);
  expect(traffic.errors).toEqual([]);
});

test("@mobile a short landscape viewport keeps map controls and schematic usable", async ({
  page,
}) => {
  const traffic = await installControlledTiles(page);
  await page.setViewportSize({ width: 320, height: 600 });
  await openMap(page);
  const pane = await page.locator(".leaflet-map-pane").elementHandle();
  await page.setViewportSize({ width: 844, height: 390 });
  await settleMap(page);
  await retained(page, pane, ".leaflet-map-pane");
  const surface = await page.locator(".map-surface").boundingBox();
  const controls = await page.locator(".map-controls").boundingBox();
  expect(surface).not.toBeNull();
  expect(controls).not.toBeNull();
  expect(surface!.height).toBeGreaterThanOrEqual(280);
  expect(controls!.y).toBeGreaterThanOrEqual(surface!.y);
  expect(controls!.y + controls!.height).toBeLessThanOrEqual(
    surface!.y + surface!.height,
  );
  await page.getByRole("button", { name: "Phóng to", exact: true }).click();
  await settleMap(page);
  await page
    .getByRole("button", { name: "Mở rộng bản đồ", exact: true })
    .click();
  await settleMap(page);
  await page.getByRole("button", { name: "Xem sơ đồ", exact: true }).click();
  await expect(page.getByTestId("offline-map")).toBeVisible();
  const chart = await page.locator(".atlas-chart").boundingBox();
  expect(chart).not.toBeNull();
  expect(chart!.width).toBeGreaterThan(0);
  expect(chart!.height).toBeGreaterThan(0);
  await page
    .getByRole("button", { name: "Quay lại bản đồ", exact: true })
    .click();
  await settleMap(page);
  await page
    .getByRole("button", { name: "Thu gọn bản đồ", exact: true })
    .click();
  await settleMap(page);
  await retained(page, pane, ".leaflet-map-pane");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(traffic.documents).toHaveLength(1);
  expect(traffic.errors).toEqual([]);
});
