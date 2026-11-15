import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { chromium, defineConfig, devices } from "@playwright/test";

const apiIntegration = process.env.RUN_API_INTEGRATION === "1";
const liveIntegration = process.env.RUN_LIVE_UI === "1";
const usesBackend = apiIntegration || liveIntegration;
const testOrigin = "http://127.0.0.1:5174";

function browserExecutable() {
  const explicitPath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE?.trim();
  if (explicitPath) {
    if (!existsSync(explicitPath)) {
      throw new Error(
        `PLAYWRIGHT_CHROMIUM_EXECUTABLE does not exist: ${explicitPath}`,
      );
    }
    return explicitPath;
  }

  // npm ci installs Playwright, but its browser download is a separate step.
  // Prefer its matching browser, then an installed Chrome/Edge for local use.
  const bundledPath = chromium.executablePath();
  if (existsSync(bundledPath)) return bundledPath;

  const systemPaths =
    process.platform === "win32"
      ? [
          process.env.PROGRAMFILES,
          process.env["PROGRAMFILES(X86)"],
          process.env.LOCALAPPDATA,
        ]
          .filter((root): root is string => Boolean(root))
          .flatMap((root) => [
            join(root, "Google", "Chrome", "Application", "chrome.exe"),
            join(root, "Microsoft", "Edge", "Application", "msedge.exe"),
          ])
      : process.platform === "darwin"
        ? ["/Applications", join(homedir(), "Applications")].flatMap((root) => [
            join(
              root,
              "Google Chrome.app",
              "Contents",
              "MacOS",
              "Google Chrome",
            ),
            join(
              root,
              "Microsoft Edge.app",
              "Contents",
              "MacOS",
              "Microsoft Edge",
            ),
          ])
        : [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/microsoft-edge",
          ];
  const installedPath = systemPaths.find((path) => existsSync(path));
  if (installedPath) return installedPath;

  throw new Error(
    "No E2E browser found. Run `npx playwright install chromium`, then retry `npm run test:e2e`.",
  );
}

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: liveIntegration
    ? "**/ai-live-ui.spec.ts"
    : apiIntegration
      ? "**/api-live.spec.ts"
      : "**/app.spec.ts",
  timeout: 30000,
  expect: { timeout: 10000 },
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: liveIntegration ? 0 : process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: testOrigin,
    headless: true,
    trace: liveIntegration ? "off" : "retain-on-failure",
    video: "off",
    screenshot: "only-on-failure",
    locale: "vi-VN",
    timezoneId: "Asia/Ho_Chi_Minh",
    serviceWorkers: "block",
    launchOptions: {
      executablePath: browserExecutable(),
      args: [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--use-gl=angle",
        "--use-angle=swiftshader",
        "--no-zygote",
      ],
    },
  },
  projects: [
    {
      name: "desktop",
      grepInvert: /@mobile/,
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
    ...(!usesBackend
      ? [
          {
            name: "mobile",
            grep: /@mobile/,
            use: {
              ...devices["iPhone 13"],
              browserName: "chromium" as const,
            },
          },
        ]
      : []),
  ],
  webServer: {
    command: "npm run dev -- --port 5174 --strictPort",
    url: testOrigin,
    reuseExistingServer: false,
    timeout: 60000,
    env: {
      VITE_FRONTEND_MODE: usesBackend ? "api" : "preview",
      VITE_API_BASE_URL: usesBackend
        ? process.env.VITE_API_BASE_URL || "/api/v1"
        : "/api/v1",
      VITE_ALLOW_LIVE_MODEL_CALLS: liveIntegration ? "true" : "false",
      BACKEND_PROXY_TARGET: liveIntegration
        ? "http://127.0.0.1:8002"
        : "http://127.0.0.1:8001",
      VITE_MAP_TILE_URL: "",
    },
  },
});
