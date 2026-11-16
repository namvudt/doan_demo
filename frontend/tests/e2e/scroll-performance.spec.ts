import { expect, test, type Page } from "@playwright/test";

const TILE = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=",
  "base64",
);

type Traffic = { documents: string[]; errors: string[] };

async function isolatedTraffic(page: Page): Promise<Traffic> {
  const traffic: Traffic = { documents: [], errors: [] };
  page.on("request", (request) => {
    if (request.resourceType() === "document") {
      traffic.documents.push(request.url());
    }
  });
  page.on("pageerror", (error) => traffic.errors.push(error.message));
  await page.route(/^https?:\/\//, async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname === "tiles.test") {
      await route.fulfill({ contentType: "image/png", body: TILE });
    } else if (url.hostname === "localhost" || url.hostname === "127.0.0.1") {
      await route.continue();
    } else {
      await route.abort("blockedbyclient");
    }
  });
  return traffic;
}

async function checkHeader(page: Page) {
  const header = page.locator(".app-topbar");
  await expect(header).toBeVisible();
  await expect(header.locator(".topbar-path strong")).toBeVisible();
  expect(
    await header.evaluate(
      (element) => getComputedStyle(element).backdropFilter,
    ),
  ).toBe("none");
  const bounds = await header.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.y).toBeGreaterThanOrEqual(-1);
}

async function scrollDocumentRoundTrip(page: Page) {
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollHeight - innerHeight),
    )
    .toBeGreaterThan(40);
  const viewport = page.viewportSize()!;
  await page.mouse.move(viewport.width / 2, viewport.height * 0.4);
  await page.mouse.wheel(0, 550);
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(40);
  await checkHeader(page);
  await page.mouse.wheel(0, -1600);
  await expect.poll(() => page.evaluate(() => scrollY)).toBeLessThanOrEqual(1);
  await checkHeader(page);
}

test("native wheel scrolls catalog, detail and chat without reloading", async ({
  page,
}) => {
  const traffic = await isolatedTraffic(page);
  await page.setViewportSize({ width: 1280, height: 720 });
  for (const path of [
    "/heritages",
    "/heritages/preview-heritage-thap-rua",
    "/chat",
  ]) {
    await page.goto(path);
    await expect(page.locator("main h1")).toBeVisible();
    const documents = traffic.documents.length;
    const heading = await page.locator("main h1").textContent();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollHeight - innerHeight,
    );
    if (path === "/chat" && overflow <= 40) {
      // A compact composer may fit the viewport. Do not force a regression to
      // the former long page merely to make a scroll assertion pass.
      const action = page.getByRole("button", {
        name: "Khám phá",
        exact: true,
      });
      await expect(action).toBeVisible();
      const bounds = await action.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(720);
      await checkHeader(page);
    } else {
      await scrollDocumentRoundTrip(page);
    }
    await expect(page.locator("main h1")).toHaveText(heading || "");
    expect(traffic.documents).toHaveLength(documents);
  }
  expect(traffic.errors).toEqual([]);
});

test("wheel over map results scrolls the list without zooming the map", async ({
  page,
}) => {
  const traffic = await isolatedTraffic(page);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/map");
  await expect(page.locator(".map-experience")).toHaveAttribute(
    "data-map-mode",
    "online",
  );
  await expect(page.locator(".leaflet-tile-loaded").first()).toBeVisible();
  const pane = await page.locator(".leaflet-map-pane").elementHandle();
  const zoom = await page
    .locator(".leaflet-tile")
    .first()
    .evaluate((image) => {
      return new URL((image as HTMLImageElement).src).pathname.split("/")[1];
    });
  const results = page.locator(".map-results");
  expect(
    await results.evaluate(
      (element) => element.scrollHeight - element.clientHeight,
    ),
  ).toBeGreaterThan(40);
  const bounds = await results.boundingBox();
  expect(bounds).not.toBeNull();
  await page.mouse.move(
    bounds!.x + bounds!.width / 2,
    bounds!.y + bounds!.height / 2,
  );
  await page.mouse.wheel(0, 400);
  await expect
    .poll(() => results.evaluate((element) => element.scrollTop))
    .toBeGreaterThan(20);
  await page.mouse.wheel(0, -800);
  await expect
    .poll(() => results.evaluate((element) => element.scrollTop))
    .toBe(0);
  expect(await pane!.evaluate((node) => node.isConnected)).toBe(true);
  expect(
    await page
      .locator(".leaflet-tile")
      .first()
      .evaluate((image) => {
        return new URL((image as HTMLImageElement).src).pathname.split("/")[1];
      }),
  ).toBe(zoom);
  expect(traffic.documents).toHaveLength(1);
  expect(traffic.errors).toEqual([]);
});

test("pending image feedback scrolls and reduced motion stops its animation", async ({
  page,
}) => {
  const traffic = await isolatedTraffic(page);
  let releaseImage!: () => void;
  const imageGate = new Promise<void>((resolve) => {
    releaseImage = resolve;
  });
  await page.route("**/demo-thap-rua.jpg", async (route) => {
    await imageGate;
    await route.continue();
  });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  try {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/heritages", { waitUntil: "domcontentloaded" });
    const loader = page.locator(".heritage-card .image-loading").first();
    await expect(loader).toBeVisible();
    await expect
      .poll(() =>
        loader.evaluate(
          (element) => element.getAnimations({ subtree: true }).length,
        ),
      )
      .toBeGreaterThan(0);
    const animatedProperties = await loader.evaluate((element) => {
      return element.getAnimations({ subtree: true }).flatMap((animation) => {
        return (animation.effect as KeyframeEffect)
          .getKeyframes()
          .flatMap((frame) => Object.keys(frame));
      });
    });
    // Animation remains on compositable properties rather than repainting a
    // gradient or changing layout on every frame. No wall-clock FPS assertion.
    expect(animatedProperties).toContain("transform");
    expect(
      animatedProperties.some((property) =>
        /^(background|filter|width|height|left|top)/i.test(property),
      ),
    ).toBe(false);
    await scrollDocumentRoundTrip(page);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await expect
      .poll(() =>
        loader.evaluate(
          (element) =>
            element
              .getAnimations({ subtree: true })
              .filter((animation) => animation.playState === "running").length,
        ),
      )
      .toBe(0);
    expect(traffic.documents).toHaveLength(1);
    expect(traffic.errors).toEqual([]);
  } finally {
    releaseImage();
    await page.unrouteAll({ behavior: "ignoreErrors" });
  }
});

test("@mobile native wheel scrolls catalog and detail while navigation stays available", async ({
  page,
}) => {
  const traffic = await isolatedTraffic(page);
  for (const path of ["/heritages", "/heritages/preview-heritage-thap-rua"]) {
    await page.goto(path);
    await expect(page.locator("main h1")).toBeVisible();
    const documents = traffic.documents.length;
    await scrollDocumentRoundTrip(page);
    await expect(
      page.getByRole("button", { name: "Mở điều hướng" }),
    ).toBeVisible();
    expect(traffic.documents).toHaveLength(documents);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  expect(traffic.errors).toEqual([]);
});
