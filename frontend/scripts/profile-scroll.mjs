import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const options = Object.fromEntries(
  process.argv.slice(2).map((value) => {
    const separator = value.indexOf("=");
    if (!value.startsWith("--") || separator < 0)
      throw new Error("Use --name=value arguments.");
    return [value.slice(2, separator), value.slice(separator + 1)];
  }),
);
const origin = new URL(options.origin || "http://127.0.0.1:5175");
if (!["127.0.0.1", "localhost"].includes(origin.hostname))
  throw new Error("This diagnostic only runs against a local preview server.");
const cpuRate = Number(options.cpu || 4);
const runs = Number(options.runs || 3);
if (!(cpuRate >= 1 && cpuRate <= 6 && runs >= 1 && runs <= 5))
  throw new Error("Use cpu=1..6 and runs=1..5.");
const executablePath = [
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
  chromium.executablePath(),
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
].find((file) => file && existsSync(file));
if (!executablePath)
  throw new Error("Install Chromium or configure its executable.");
const browser = await chromium.launch({ executablePath, headless: true });
const tile = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=",
  "base64",
);
const scenarios = [
  { name: "catalog-desktop", path: "/heritages", width: 1366, height: 768 },
  { name: "catalog-mobile", path: "/heritages", width: 390, height: 844 },
  {
    name: "detail-desktop",
    path: "/heritages/preview-heritage-van-mieu",
    width: 1366,
    height: 768,
  },
  { name: "chat-desktop", path: "/chat", width: 1366, height: 768 },
  {
    name: "map-list-desktop",
    path: "/map",
    width: 1366,
    height: 768,
    target: ".map-results",
  },
  {
    name: "catalog-pending-images",
    path: "/heritages",
    width: 1366,
    height: 768,
    pending: true,
  },
].filter((item) => !options.scenario || item.name === options.scenario);
if (!scenarios.length) throw new Error("Unknown scenario.");

function percentile(values, percent) {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted.length
    ? Number(
        sorted[
          Math.max(0, Math.ceil((percent / 100) * sorted.length) - 1)
        ].toFixed(2),
      )
    : 0;
}

async function profile(scenario) {
  const context = await browser.newContext({
    viewport: { width: scenario.width, height: scenario.height },
    reducedMotion: "no-preference",
    serviceWorkers: "block",
  });
  const page = await context.newPage();
  const errors = [];
  let documents = 0;
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (request.resourceType() === "document") documents += 1;
  });
  const pendingImages = [];
  await page.route(/^https?:\/\//, async (route) => {
    const url = new URL(route.request().url());
    if (!["127.0.0.1", "localhost"].includes(url.hostname)) {
      // Exercise Leaflet without contacting a community or keyed tile service.
      if (
        [
          "tiles.test",
          "tile.openstreetmap.de",
          "tile.openstreetmap.org",
        ].includes(url.hostname)
      )
        await route.fulfill({ contentType: "image/png", body: tile });
      else await route.abort();
    } else if (
      scenario.pending &&
      route.request().resourceType() === "image" &&
      url.pathname.startsWith("/heritages/")
    ) {
      pendingImages.push(route);
    } else await route.continue();
  });
  const cdp = await context.newCDPSession(page);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: cpuRate });
  await cdp.send("Performance.enable");
  await page.goto(new URL(scenario.path, origin).href, {
    waitUntil: "domcontentloaded",
  });
  await page.locator("main h1").first().waitFor();
  await page.evaluate(() => document.fonts.ready);
  if (options.noBlur === "true")
    await page.addStyleTag({
      content:
        ".app-topbar{backdrop-filter:none!important;background:#101a17!important}",
    });
  if (!scenario.pending) {
    // Native lazy-load thresholds differ across viewports. Explicitly finish
    // local image decoding before measuring steady scroll; the separate
    // pending-images case retains the real loading placeholders.
    await page.evaluate(async () => {
      await Promise.all(
        [...document.images].map(async (image) => {
          image.loading = "eager";
          try {
            await image.decode();
          } catch {
            /* Error UI is measured separately. */
          }
        }),
      );
    });
    await page.waitForFunction(
      () => !document.querySelector(".resilient-image.loading"),
    );
  }
  const target = scenario.target
    ? page.locator(scenario.target)
    : page.locator("main");
  const bounds = await target.boundingBox();
  if (!bounds) throw new Error(`No scroll target: ${scenario.name}`);
  const x = Math.round(
    Math.min(scenario.width - 30, Math.max(40, bounds.x + bounds.width * 0.6)),
  );
  const y = Math.round(
    Math.max(120, Math.min(scenario.height * 0.6, bounds.y + 150)),
  );
  const before = Object.fromEntries(
    (await cdp.send("Performance.getMetrics")).metrics.map((metric) => [
      metric.name,
      metric.value,
    ]),
  );
  await page.evaluate(() => {
    const data = { frames: [], longTasks: [], active: true, previous: 0 };
    window.__scrollProfile = data;
    data.observer = new PerformanceObserver((list) => {
      data.longTasks.push(...list.getEntries().map((entry) => entry.duration));
    });
    data.observer.observe({ type: "longtask" });
    function frame(time) {
      if (!data.active) return;
      if (data.previous) data.frames.push(time - data.previous);
      data.previous = time;
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  });
  await cdp.send("Tracing.start", {
    categories: "devtools.timeline,cc",
    transferMode: "ReturnAsStream",
  });
  const start = await page.evaluate(
    (selector) =>
      selector ? document.querySelector(selector).scrollTop : scrollY,
    scenario.target,
  );
  const scrollPositions = [];
  for (const distance of [-1000, 1000, -1000, 1000]) {
    await cdp.send("Input.synthesizeScrollGesture", {
      x,
      y,
      yDistance: distance,
      speed: 1400,
      gestureSourceType: "mouse",
    });
    scrollPositions.push(
      await page.evaluate(
        (selector) =>
          selector ? document.querySelector(selector).scrollTop : scrollY,
        scenario.target,
      ),
    );
  }
  const measurement = await page.evaluate((selector) => {
    const data = window.__scrollProfile;
    data.active = false;
    data.observer.disconnect();
    return {
      frames: data.frames,
      longTasks: data.longTasks,
      finalScroll: selector
        ? document.querySelector(selector).scrollTop
        : scrollY,
      imageLoaders: document.querySelectorAll(".image-loading").length,
      topbarBackdrop: getComputedStyle(document.querySelector(".app-topbar"))
        .backdropFilter,
    };
  }, scenario.target);
  const endTrace = new Promise((resolveTrace) =>
    cdp.once("Tracing.tracingComplete", resolveTrace),
  );
  await cdp.send("Tracing.end");
  const { stream } = await endTrace;
  let traceText = "";
  for (;;) {
    const chunk = await cdp.send("IO.read", { handle: stream });
    traceText += chunk.data;
    if (chunk.eof) break;
  }
  await cdp.send("IO.close", { handle: stream });
  const trace = JSON.parse(traceText).traceEvents;
  const paints = trace.filter(
    (event) => event.name === "Paint" && event.ph === "X",
  );
  const rasters = trace.filter(
    (event) => event.name === "RasterTask" && event.ph === "X",
  );
  const after = Object.fromEntries(
    (await cdp.send("Performance.getMetrics")).metrics.map((metric) => [
      metric.name,
      metric.value,
    ]),
  );
  const result = {
    scenario: scenario.name,
    frameSamples: measurement.frames.length,
    frameMedianMs: percentile(measurement.frames, 50),
    frameP95Ms: percentile(measurement.frames, 95),
    framesOver32Ms: measurement.frames.filter((value) => value > 32).length,
    longTasks: measurement.longTasks.length,
    longTaskMaxMs: percentile(measurement.longTasks, 100),
    paintEvents: paints.length,
    paintMs: Number(
      (paints.reduce((sum, event) => sum + event.dur, 0) / 1000).toFixed(2),
    ),
    rasterTasks: rasters.length,
    rasterMs: Number(
      (rasters.reduce((sum, event) => sum + event.dur, 0) / 1000).toFixed(2),
    ),
    taskMs: Number(
      ((after.TaskDuration - before.TaskDuration) * 1000).toFixed(2),
    ),
    scriptMs: Number(
      ((after.ScriptDuration - before.ScriptDuration) * 1000).toFixed(2),
    ),
    layoutCount: after.LayoutCount - before.LayoutCount,
    layoutMs: Number(
      ((after.LayoutDuration - before.LayoutDuration) * 1000).toFixed(2),
    ),
    imageLoaders: measurement.imageLoaders,
    topbarBackdrop: measurement.topbarBackdrop,
    startScroll: start,
    finalScroll: measurement.finalScroll,
    scrollPositions,
    documentRequests: documents,
    errors,
  };
  await context.close();
  return result;
}

const results = [];
try {
  for (let iteration = 0; iteration < runs; iteration += 1) {
    for (const scenario of scenarios) {
      const result = { run: iteration + 1, ...(await profile(scenario)) };
      results.push(result);
      console.log(JSON.stringify(result));
    }
  }
} finally {
  await browser.close();
}
const output = resolve(
  options.output ||
    `artifacts/performance/scroll-${options.label || "local"}.json`,
);
mkdirSync(dirname(output), { recursive: true });
writeFileSync(
  output,
  JSON.stringify(
    {
      label: options.label || "local",
      environment: {
        cpuSlowdown: cpuRate,
        runs,
        headless: true,
        viewportPerScenario: true,
        externalRequests: "blocked; map tiles fulfilled locally",
        noBlurOverride: options.noBlur === "true",
      },
      results,
    },
    null,
    2,
  ) + "\n",
);
console.log(`Saved ${results.length} samples to ${output}`);
