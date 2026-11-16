import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

// No .env file is loaded. A live run requires an explicitly supplied user key.
const args = new Set(process.argv.slice(2));
const deniedSelfTest = args.has("--self-test-denied");
const selfTest = args.has("--self-test") || deniedSelfTest;
const liveRun = args.has("--run");
const providerArgument = process.argv.find((value) =>
  value.startsWith("--provider="),
);
const providerIndex = process.argv.indexOf("--provider");
const providerName =
  providerArgument?.slice("--provider=".length) ||
  (providerIndex >= 0 ? process.argv[providerIndex + 1] : "maptiler");
const maptilerKey = process.env.MAPTILER_API_KEY?.trim();
const mapboxToken =
  process.env.MAPBOX_ACCESS_TOKEN?.trim() ||
  process.env.VITE_MAPBOX_ACCESS_TOKEN?.trim();
const configuredKey = providerName === "mapbox" ? mapboxToken : maptilerKey;
const tileSize = providerName === "mapbox" ? 512 : 256;
const zoomOffset = providerName === "mapbox" ? -1 : 0;
const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outputArg = process.argv.indexOf("--output");
const outputPath = outputArg >= 0 ? process.argv[outputArg + 1] : undefined;
const viewport = { width: 960, height: 540 };
const maxTileRequests = 64;

function redact(message, key = configuredKey) {
  let text = String(message);
  for (const value of new Set(
    [key, maptilerKey, mapboxToken].filter(Boolean),
  )) {
    text = text.split(value).join("[redacted]");
    text = text.split(encodeURIComponent(value)).join("[redacted]");
  }
  text = text.replace(/\b(?:pk|sk)\.[A-Za-z0-9_.-]+/g, "[redacted token]");
  return text.replace(/https?:\/\/[^\s"'<>]+/g, (candidate) => {
    try {
      const url = new URL(candidate);
      return `${url.origin}${url.pathname}${url.search ? "?[redacted]" : ""}`;
    } catch {
      return "[redacted URL]";
    }
  });
}

function percentile(values, fraction) {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  return sorted.length
    ? Math.round(
        sorted[Math.max(0, Math.ceil(sorted.length * fraction) - 1)] * 10,
      ) / 10
    : null;
}

function distribution(values) {
  return {
    samples: values.length,
    p50: percentile(values, 0.5),
    p95: percentile(values, 0.95),
  };
}

function browserExecutable() {
  const supplied = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE?.trim();
  const candidates = [
    supplied,
    chromium.executablePath(),
    ...[
      process.env.PROGRAMFILES,
      process.env["PROGRAMFILES(X86)"],
      process.env.LOCALAPPDATA,
    ]
      .filter(Boolean)
      .flatMap((root) => [
        join(root, "Google", "Chrome", "Application", "chrome.exe"),
        join(root, "Microsoft", "Edge", "Application", "msedge.exe"),
      ]),
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ];
  const executable = candidates.find(
    (candidate) => candidate && existsSync(candidate),
  );
  if (!executable)
    throw new Error(
      "No browser found; install Playwright Chromium or set PLAYWRIGHT_CHROMIUM_EXECUTABLE.",
    );
  return executable;
}

function viewerHtml(tileTemplate) {
  const providerCredit = selfTest
    ? "Local PNG fixture, not map-provider data"
    : providerName === "mapbox"
      ? '<a href="https://www.mapbox.com/about/maps/">&copy; Mapbox</a> <a href="https://www.openstreetmap.org/copyright/">&copy; OpenStreetMap</a> <a href="https://apps.mapbox.com/feedback/#/105.8542/21.0285/12">Improve this map</a>'
      : '<a href="https://www.maptiler.com/copyright/">&copy; MapTiler</a> <a href="https://www.openstreetmap.org/copyright">&copy; OpenStreetMap contributors</a>';
  const logo = selfTest
    ? ""
    : providerName === "mapbox"
      ? '<a class="provider-logo" href="https://www.mapbox.com/"><img src="/mapbox-logo.svg" alt="Mapbox logo" style="height:30px;width:auto"></a>'
      : '<a class="provider-logo" href="https://www.maptiler.com"><img src="https://api.maptiler.com/resources/logo.svg" alt="MapTiler logo"></a>';
  return `<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bounded map provider experiment</title><link rel="stylesheet" href="/leaflet.css">
<style>html,body,#map{margin:0;width:100%;height:100%;} .provider-logo{position:absolute;bottom:8px;left:8px;z-index:1000;} .provider-logo img{width:100px;} </style>
</head><body><div id="map">${logo}</div><script src="/leaflet.js"></script><script>
const map=L.map('map',{zoomControl:false,zoomAnimation:false,fadeAnimation:false,markerZoomAnimation:false,dragging:false,scrollWheelZoom:false,doubleClickZoom:false,touchZoom:false,boxZoom:false,keyboard:false}).setView([21.0285,105.8542],12);
const started=performance.now();
const result=window.__benchmark={done:false,loaded:0,failed:0,decodedReadyMs:null,settledMs:null};
const tiles=L.tileLayer(${JSON.stringify(tileTemplate)},{tileSize:${tileSize},zoomOffset:${zoomOffset},maxZoom:18,keepBuffer:0,updateWhenIdle:true,updateWhenZooming:false,attribution:${JSON.stringify(providerCredit)}});
tiles.on('tileload',()=>result.loaded++);
tiles.on('tileerror',()=>result.failed++);
tiles.once('load',async()=>{
  result.settledMs=performance.now()-started;
  const images=Array.from(document.querySelectorAll('.leaflet-tile'));
  const decoded=await Promise.all(images.map(image=>image.decode().then(()=>true,()=>false)));
  if(!result.failed && decoded.every(Boolean)) result.decodedReadyMs=performance.now()-started;
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  result.done=true;
});
tiles.addTo(map);
</script></body></html>`;
}

async function printReport(report) {
  const serialized = JSON.stringify(report, null, 2);
  if (outputPath) {
    const destination = resolve(outputPath);
    await mkdir(dirname(destination), { recursive: true });
    await writeFile(destination, `${serialized}\n`, "utf8");
  }
  process.stdout.write(`${serialized}\n`);
}

async function main() {
  if (!["maptiler", "mapbox"].includes(providerName)) {
    throw new Error("--provider must be maptiler or mapbox.");
  }
  if (outputArg >= 0 && !outputPath) {
    throw new Error("--output requires a destination path.");
  }
  if (args.has("--help")) {
    process.stdout.write(
      "node scripts/map-provider-benchmark.mjs --check | --self-test | --self-test-denied | --run [--provider=maptiler|mapbox] [--headed] [--output path]\nLive mode reads MAPTILER_API_KEY or MAPBOX_ACCESS_TOKEN/VITE_MAPBOX_ACCESS_TOKEN from the process environment only.\n",
    );
    return;
  }
  if (!selfTest && !liveRun) {
    await printReport({
      mode: "credential-check-only",
      selectedProvider: providerName,
      networkRequests: 0,
      providers: {
        maptiler: {
          credentialConfigured: Boolean(maptilerKey),
          liveAdapter: true,
        },
        mapbox: {
          credentialConfigured: Boolean(mapboxToken),
          browserTokenType: !mapboxToken
            ? "missing"
            : mapboxToken.startsWith("pk.")
              ? "public"
              : mapboxToken.startsWith("sk.")
                ? "secret-rejected"
                : "unsupported-rejected",
          liveAdapter: true,
        },
        goong: {
          credentialConfigured: Boolean(process.env.GOONG_MAPTILES_KEY),
          liveAdapter: false,
        },
        vietmap: {
          credentialConfigured: Boolean(process.env.VIETMAP_API_KEY),
          liveAdapter: false,
        },
      },
      communityTiles:
        "Excluded from automated benchmark; use normal human viewing under provider policy.",
      instruction:
        "Supply your own restricted provider browser key and opt in with --run. The script itself does not load .env files; Node --env-file can explicitly load a selected frontend-only file.",
    });
    return;
  }
  if (!selfTest && !configuredKey) {
    throw new Error(
      `${providerName === "mapbox" ? "MAPBOX_ACCESS_TOKEN/VITE_MAPBOX_ACCESS_TOKEN" : "MAPTILER_API_KEY"} is not configured; no provider request was sent.`,
    );
  }
  if (
    !selfTest &&
    providerName === "mapbox" &&
    !mapboxToken.startsWith("pk.")
  ) {
    throw new Error(
      "Mapbox browser benchmark requires a public pk. token; secret sk. and other token types are rejected before any request.",
    );
  }
  const requestedPort = selfTest
    ? 0
    : Number(process.env.MAP_BENCH_PORT || 5177);
  if (
    !Number.isInteger(requestedPort) ||
    requestedPort < 0 ||
    requestedPort > 65535
  ) {
    throw new Error("MAP_BENCH_PORT must be an integer port.");
  }
  const tilePath =
    providerName === "mapbox"
      ? "/styles/v1/mapbox/streets-v12/tiles/512/{z}/{x}/{y}"
      : "/maps/streets-v4/256/{z}/{x}/{y}.png";
  const queryName = providerName === "mapbox" ? "access_token" : "key";
  const tileTemplate = `${selfTest ? "" : providerName === "mapbox" ? "https://api.mapbox.com" : "https://api.maptiler.com"}${tilePath}?${queryName}=${encodeURIComponent(selfTest ? "fixture-redaction-token" : configuredKey)}`;
  // The app and this viewer share the unmodified official Mapbox asset.
  const mapboxLogo =
    !selfTest && providerName === "mapbox"
      ? await readFile(join(frontendRoot, "public", "mapbox-logo-white.svg"))
      : null;
  const fixture = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=",
    "base64",
  );
  const leafletFiles = new Map([
    ["/leaflet.js", ["application/javascript", "leaflet.js"]],
    ["/leaflet.css", ["text/css", "leaflet.css"]],
  ]);
  const server = createServer(async (request, response) => {
    const pathname = new URL(request.url, "http://localhost").pathname;
    if (pathname === "/") {
      response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      response.end(viewerHtml(tileTemplate));
    } else if (pathname === "/mapbox-logo.svg" && mapboxLogo) {
      response.writeHead(200, {
        "Content-Type": "image/svg+xml",
        "Cache-Control": "public, max-age=3600",
      });
      response.end(mapboxLogo);
    } else if (leafletFiles.has(pathname)) {
      const [type, filename] = leafletFiles.get(pathname);
      response.writeHead(200, {
        "Content-Type": type,
        "Cache-Control": "public, max-age=3600",
      });
      response.end(
        await readFile(
          join(frontendRoot, "node_modules", "leaflet", "dist", filename),
        ),
      );
    } else if (
      selfTest &&
      /\/(?:256\/)?\d+\/\d+\/\d+(?:\.png)?$/.test(pathname)
    ) {
      response.writeHead(deniedSelfTest ? 403 : 200, {
        "Content-Type": deniedSelfTest ? "text/plain" : "image/png",
        "Cache-Control": deniedSelfTest ? "no-store" : "public, max-age=3600",
      });
      response.end(deniedSelfTest ? "Forbidden fixture" : fixture);
    } else {
      response.writeHead(404).end();
    }
  });
  let browser;
  try {
    await new Promise((accept, reject) => {
      server.once("error", reject);
      server.listen(requestedPort, "127.0.0.1", accept);
    });
    const origin = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch({
      executablePath: browserExecutable(),
      headless: !args.has("--headed"),
    });
    const context = await browser.newContext({
      viewport,
      serviceWorkers: "block",
    });
    const page = await context.newPage();
    const session = await context.newCDPSession(page);
    await session.send("Network.enable");
    await session.send("Network.setCacheDisabled", { cacheDisabled: false });
    let entries = new Map();
    let totalTileRequests = 0;
    const errors = [];
    const externalHosts = new Set();
    const isTile = (url) => /\/\d+\/\d+\/\d+(?:\.png)?(?:\?|$)/.test(url);
    page.on("pageerror", (error) => errors.push(redact(error.message)));
    page.on("request", (request) => {
      const host = new URL(request.url()).hostname;
      if (host !== "127.0.0.1") externalHosts.add(host);
    });
    session.on("Network.requestWillBeSent", (event) => {
      if (!isTile(event.request.url)) return;
      totalTileRequests++;
      entries.set(event.requestId, { started: event.timestamp, cached: false });
      if (totalTileRequests > maxTileRequests) void context.close();
    });
    session.on("Network.requestServedFromCache", (event) => {
      const entry = entries.get(event.requestId);
      if (entry) entry.cached = true;
    });
    session.on("Network.responseReceived", (event) => {
      const entry = entries.get(event.requestId);
      if (!entry) return;
      entry.status = event.response.status;
      entry.cached ||= Boolean(
        event.response.fromDiskCache || event.response.fromPrefetchCache,
      );
      const timing = event.response.timing;
      if (timing && timing.receiveHeadersStart >= 0)
        entry.headerMs =
          (timing.requestTime - entry.started) * 1000 +
          timing.receiveHeadersStart;
    });
    session.on("Network.loadingFinished", (event) => {
      const entry = entries.get(event.requestId);
      if (entry) entry.completeMs = (event.timestamp - entry.started) * 1000;
    });
    session.on("Network.loadingFailed", (event) => {
      const entry = entries.get(event.requestId);
      if (entry) entry.failed = true;
    });
    const phases = [];
    for (const name of ["cold-context", "warm-reload"]) {
      entries = new Map();
      if (name === "cold-context")
        await page.goto(origin, { waitUntil: "domcontentloaded" });
      else await page.reload({ waitUntil: "domcontentloaded" });
      let timedOut = false;
      await page
        .waitForFunction(() => window.__benchmark?.done, undefined, {
          timeout: 20000,
        })
        .catch(() => {
          timedOut = true;
        });
      const decoded = await page.evaluate(() => window.__benchmark);
      const requests = [...entries.values()];
      const uncached = requests.filter(
        (entry) => !entry.cached && entry.status === 200,
      );
      const statuses = {};
      for (const entry of requests)
        statuses[entry.status || "no-response"] =
          (statuses[entry.status || "no-response"] || 0) + 1;
      phases.push({
        phase: name,
        tileRequests: requests.length,
        browserCacheHits: requests.filter((entry) => entry.cached).length,
        failedRequests: requests.filter((entry) => entry.failed).length,
        statuses,
        uncachedHeaderMs: distribution(
          uncached.map((entry) => entry.headerMs).filter(Number.isFinite),
        ),
        uncachedCompleteMs: distribution(
          uncached.map((entry) => entry.completeMs).filter(Number.isFinite),
        ),
        tileLoaded: decoded.loaded,
        tileErrors: decoded.failed,
        allTilesSettledMs:
          decoded.settledMs === null
            ? null
            : Math.round(decoded.settledMs * 10) / 10,
        allTilesDecodedReadyMs:
          decoded.decodedReadyMs === null
            ? null
            : Math.round(decoded.decodedReadyMs * 10) / 10,
        timedOut,
      });
      // An authentication/referrer failure is not a reason to spend more quota.
      if (
        requests.some((entry) => entry.status === 401 || entry.status === 403)
      )
        break;
    }
    if (selfTest) {
      assert.equal(errors.length, 0);
      assert.equal(externalHosts.size, 0);
      if (deniedSelfTest) {
        assert.equal(phases.length, 1);
        assert(phases[0].statuses[403] > 0);
        assert.equal(phases[0].allTilesDecodedReadyMs, null);
        assert(phases[0].tileErrors > 0);
      } else {
        assert(
          phases.every(
            (phase) =>
              phase.tileLoaded > 0 && !phase.tileErrors && !phase.timedOut,
          ),
        );
        assert(phases[1].browserCacheHits > 0);
      }
      const sentinel = "fixture-redaction-token";
      assert(
        !redact(
          `https://example.invalid/tile.png?key=${sentinel} ${sentinel}`,
          sentinel,
        ).includes(sentinel),
      );
      assert(
        !redact("pk.fixture.public sk.fixture.secret").includes("fixture"),
      );
      assert(totalTileRequests <= maxTileRequests);
    }
    const successful = phases.every(
      (phase) => phase.tileLoaded > 0 && !phase.tileErrors && !phase.timedOut,
    );
    await printReport({
      mode: deniedSelfTest
        ? "local-fixture-403-self-test"
        : selfTest
          ? "local-fixture-self-test"
          : `live-${providerName}-raster`,
      provider: providerName,
      successful,
      ...(deniedSelfTest ? { expectedFailureVerified: true } : {}),
      capturedAt: new Date().toISOString(),
      viewport,
      tileSize,
      zoomOffset,
      center: { latitude: 21.0285, longitude: 105.8542, zoom: 12 },
      totalTileRequests,
      maximumTileRequests: maxTileRequests,
      externalHostnames: [...externalHosts],
      phases,
      pageErrors: errors,
      limitations: [
        "One fixed viewport and at most two loads; small sample, not a provider ranking or SLA.",
        "Cold means a fresh browser context; CDN/server caches are not flushed.",
        "Warm reload honors normal browser/server cache headers; no cache-bypass headers or interception.",
        "Header time includes connection/request scheduling; it is not pure server processing time.",
        "No scroll FPS, app React rendering, vector SDK, search, or routing is measured.",
        "Provider adapters may use different tile sizes; compare the physical viewport, not per-tile bytes or latency as equal-sized work.",
        ...(selfTest
          ? [
              "Fixture timings are artificial local transport and must not be presented as map-provider speed.",
            ]
          : []),
      ],
    });
    if (!successful && !deniedSelfTest) process.exitCode = 1;
  } finally {
    await browser?.close();
    await new Promise((accept) => server.close(accept));
  }
}

main().catch((error) => {
  process.stderr.write(`Benchmark failed: ${redact(error.message)}\n`);
  process.exitCode = 1;
});
