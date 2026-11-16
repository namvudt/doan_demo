import { appendFile, mkdir } from "node:fs/promises";
import { expect, test, type Page, type Response } from "@playwright/test";

test.skip(
  process.env.RUN_PRODUCT_API !== "1",
  "Run explicitly against the deployed product backend.",
);
test.use({ trace: "off" });

const modelRequests = new WeakMap<Page, string[]>();
const allowModel = new WeakMap<Page, boolean>();

function responseFor(
  page: Page,
  pathname: string | RegExp,
  method = "GET",
  status = 200,
) {
  return page.waitForResponse((response: Response) => {
    const path = new URL(response.url()).pathname;
    return (
      (typeof pathname === "string"
        ? path === pathname
        : pathname.test(path)) &&
      response.request().method() === method &&
      response.status() === status
    );
  });
}

async function navigate(page: Page, path: string) {
  await page.evaluate((value) => {
    window.history.pushState(null, "", value);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);
}

async function screenshot(page: Page, filename: string) {
  for (
    let index = 0;
    index < 10 &&
    (await page
      .getByRole("button", { name: "Đóng thông báo", exact: true })
      .count());
    index += 1
  ) {
    await page
      .getByRole("button", { name: "Đóng thông báo", exact: true })
      .first()
      .click();
  }
  await page.locator("h1").first().click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  await mkdir("artifacts/screenshots/product-api", { recursive: true });
  await page.screenshot({
    path: `artifacts/screenshots/product-api/${filename}`,
    fullPage: true,
  });
}

test.beforeEach(async ({ page }) => {
  const response = await page.request.get("/api/v1/capabilities");
  expect(response.ok()).toBe(true);
  const capabilities = await response.json();
  expect(capabilities.model_mode).toBe("demo");
  expect(capabilities.features.accounts).toBe(true);
  expect(capabilities.features.conversations).toBe(true);
  expect(capabilities.features.heritage_favorites).toBe(true);
  expect(response.headers()["x-backend-build"]).toBeTruthy();
  modelRequests.set(page, []);
  allowModel.set(page, false);
  await page.route(/^https?:\/\//, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (!["127.0.0.1", "localhost"].includes(url.hostname)) {
      await route.abort("blockedbyclient");
    } else if (
      request.method() === "POST" &&
      /^\/api\/v1\/runs(?:$|\/[^/]+\/(?:retry|review|clarification|resume)$)/.test(
        url.pathname,
      )
    ) {
      modelRequests.get(page)!.push(url.pathname);
      if (!allowModel.get(page)) await route.abort("blockedbyclient");
      else await route.continue();
    } else {
      await route.continue();
    }
  });
});

test("account refresh/logout/login preserves favorites and conversations without automatic AI calls", async ({
  page,
}) => {
  const capabilities = await (
    await page.request.get("/api/v1/capabilities")
  ).json();
  expect(capabilities.model_mode).toBe("demo");
  expect(capabilities.features.accounts).toBe(true);
  expect(capabilities.features.conversations).toBe(true);
  expect(capabilities.features.heritage_favorites).toBe(true);
  const email = `qa-product-${crypto.randomUUID()}@example.test`;
  const password = "Product-fixture-password-01234";
  let token = "";
  const runPosts = modelRequests.get(page)!;
  const navigate = async (path: string) => {
    await page.evaluate((value) => {
      window.history.pushState(null, "", value);
      window.dispatchEvent(new PopStateEvent("popstate"));
    }, path);
  };
  try {
    await page.goto("/register");
    await page
      .getByRole("textbox", { name: "Tên hiển thị tài khoản", exact: true })
      .fill("Tài khoản kiểm thử");
    await page
      .getByRole("textbox", { name: "Email tài khoản", exact: true })
      .fill(email);
    await page.getByLabel("Mật khẩu tài khoản", { exact: true }).fill(password);
    await page.getByLabel("Xác nhận mật khẩu", { exact: true }).fill(password);
    const signed = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === "/api/v1/auth/sessions" &&
        response.status() === 200,
    );
    const registered = responseFor(page, "/api/v1/accounts", "POST", 201);
    await page
      .getByRole("button", { name: "Tạo tài khoản", exact: true })
      .click();
    const createdAccount = (await (await registered).json()) as {
      account_id: string;
    };
    await mkdir("../.api-demo/reports", { recursive: true });
    await appendFile(
      "../.api-demo/reports/product-e2e-accounts.jsonl",
      JSON.stringify({
        account_id: createdAccount.account_id,
        purpose: "product-ui-qa",
      }) + "\n",
      "utf8",
    );
    const issued = (await (await signed).json()) as {
      access_token: string;
      account: { account_id: string; role: string };
    };
    token = issued.access_token;
    expect(issued.account.account_id).toBe(createdAccount.account_id);
    expect(issued.account.role).toBe("user");
    await expect(page).toHaveURL(/\/profile$/);
    await expect(page.locator("main")).toContainText(email);
    const previousToken = token;
    const refreshed = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === "/api/v1/auth/refresh" &&
        response.status() === 200,
    );
    await page
      .getByRole("button", { name: "Gia hạn phiên đăng nhập", exact: true })
      .click();
    token = ((await (await refreshed).json()) as { access_token: string })
      .access_token;
    expect(token !== previousToken).toBe(true);
    expect(
      (
        await page.request.get("/api/v1/users/me", {
          headers: { Authorization: `Bearer ${previousToken}` },
        })
      ).status(),
    ).toBe(401);
    await navigate("/heritages");
    const card = page.locator(".heritage-card").first();
    const name = (await card.getByRole("heading").innerText()).trim();
    await card
      .getByRole("button", { name: "Thêm yêu thích di sản", exact: true })
      .click();
    await expect(
      card.getByRole("button", { name: "Bỏ yêu thích di sản", exact: true }),
    ).toBeVisible();
    await navigate("/favorites");
    await expect(page.locator("main")).toContainText(name);
    await navigate("/chat");
    await page
      .getByText("Hội thoại và ngữ cảnh (tùy chọn)", { exact: true })
      .click();
    await page
      .getByRole("textbox", { name: "Câu hỏi", exact: true })
      .fill("Bản nháp chưa gửi tới model");
    await page
      .getByRole("textbox", { name: "Tên hội thoại mới", exact: true })
      .fill("Chuyến khám phá kiểm thử");
    await page
      .getByRole("checkbox", {
        name: "Cho hội thoại mới dùng ngữ cảnh có giới hạn",
      })
      .check();
    await page
      .getByRole("button", { name: "Tạo hội thoại", exact: true })
      .click();
    await expect(
      page.getByRole("combobox", { name: "Hội thoại đang dùng", exact: true }),
    ).not.toHaveValue("");
    const conversationId = await page
      .getByRole("combobox", { name: "Hội thoại đang dùng", exact: true })
      .inputValue();
    await expect(
      page.getByRole("textbox", { name: "Câu hỏi", exact: true }),
    ).toHaveValue("Bản nháp chưa gửi tới model");
    expect(runPosts).toEqual([]);
    await navigate("/profile");
    const signedOut = responseFor(page, "/api/v1/sessions/me", "DELETE", 204);
    await page
      .getByRole("button", { name: "Thu hồi và đăng xuất", exact: true })
      .click();
    await signedOut;
    await expect(page).toHaveURL(/\/login$/);
    expect(
      (
        await page.request.get("/api/v1/users/me", {
          headers: { Authorization: `Bearer ${token}` },
        })
      ).status(),
    ).toBe(401);
    token = "";
    await page.reload();
    await navigate("/login");
    await page.getByRole("button", { name: "Tài khoản", exact: true }).click();
    await page
      .getByRole("textbox", { name: "Email tài khoản", exact: true })
      .fill(email);
    await page.getByLabel("Mật khẩu tài khoản", { exact: true }).fill(password);
    const second = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === "/api/v1/auth/sessions" &&
        response.status() === 200,
    );
    await page
      .getByRole("button", { name: "Đăng nhập tài khoản", exact: true })
      .click();
    token = ((await (await second).json()) as { access_token: string })
      .access_token;
    await expect(page).toHaveURL(/\/chat$/);
    await page
      .getByText("Hội thoại và ngữ cảnh (tùy chọn)", { exact: true })
      .click();
    await expect(
      page.getByRole("combobox", { name: "Hội thoại đang dùng", exact: true }),
    ).toContainText("Chuyến khám phá kiểm thử");
    await page
      .getByRole("combobox", { name: "Hội thoại đang dùng", exact: true })
      .selectOption(conversationId);
    await expect(page).toHaveURL(
      new RegExp(`/chat\\?conversation=${conversationId}$`),
    );
    await navigate("/favorites");
    await expect(page.locator("main")).toContainText(name);
    await screenshot(page, "account-favorites.png");
    expect(
      await page.evaluate(() =>
        Object.keys(localStorage).some((key) =>
          /token|password|credential/i.test(key),
        ),
      ),
    ).toBe(false);
    expect(runPosts).toEqual([]);
  } finally {
    if (token)
      await page.request.delete("/api/v1/sessions/me", {
        headers: { Authorization: `Bearer ${token}` },
      });
  }
});

test("guest explicit conversation run creates history and forgetting memory preserves that history", async ({
  page,
}) => {
  let token = "";
  const question =
    "Mô tả các chi tiết kiến trúc nhìn thấy trong ảnh để kiểm thử hội thoại.";
  try {
    await page.goto("/login");
    const createdGuest = responseFor(page, "/api/v1/sessions", "POST", 201);
    await page
      .getByRole("button", { name: "Tạo phiên khách", exact: true })
      .click();
    token = ((await (await createdGuest).json()) as { access_token: string })
      .access_token;
    await expect(page).toHaveURL(/\/chat$/);
    await page
      .getByText("Hội thoại và ngữ cảnh (tùy chọn)", { exact: true })
      .click();
    await page
      .getByRole("textbox", { name: "Tên hội thoại mới", exact: true })
      .fill("Hội thoại demo có lịch sử");
    await page
      .getByRole("checkbox", {
        name: "Cho hội thoại mới dùng ngữ cảnh có giới hạn",
      })
      .check();
    const conversationCreated = responseFor(
      page,
      "/api/v1/conversations",
      "POST",
      201,
    );
    await page
      .getByRole("button", { name: "Tạo hội thoại", exact: true })
      .click();
    const conversation = (await (await conversationCreated).json()) as {
      conversation_id: string;
    };
    await expect(
      page.getByRole("combobox", { name: "Hội thoại đang dùng", exact: true }),
    ).toHaveValue(conversation.conversation_id);
    const samples = (await (
      await page.request.get("/api/v1/samples")
    ).json()) as { items: Array<{ sample_id: string }> };
    const sample = samples.items[0]!.sample_id;
    const imageImported = responseFor(
      page,
      `/api/v1/samples/${sample}/assets`,
      "POST",
      201,
    );
    await page
      .getByRole("combobox", { name: "Ảnh mẫu từ hệ thống", exact: true })
      .selectOption(sample);
    await imageImported;
    await page
      .getByRole("textbox", { name: "Câu hỏi", exact: true })
      .fill(question);
    expect(modelRequests.get(page)).toEqual([]);
    allowModel.set(page, true);
    const runCreated = responseFor(page, "/api/v1/runs", "POST", 202);
    await page
      .getByRole("button", { name: "Gửi câu hỏi", exact: true })
      .click();
    const createdResponse = await runCreated;
    allowModel.set(page, false);
    const requestBody = createdResponse.request().postDataJSON() as {
      conversation_id: string;
      question: string;
    };
    expect(requestBody.conversation_id).toBe(conversation.conversation_id);
    expect(requestBody.question).toBe(question);
    const run = (await createdResponse.json()) as { run_id: string };
    await expect(page).toHaveURL(new RegExp(`/chat/runs/${run.run_id}$`));
    await expect(page.getByText("Đã chạy xong", { exact: true })).toBeVisible({
      timeout: 20_000,
    });
    const auth = { Authorization: `Bearer ${token}` };
    const memoryPath = `/api/v1/conversations/${conversation.conversation_id}/memory`;
    const memory = (await (
      await page.request.get(memoryPath, { headers: auth })
    ).json()) as { items: unknown[]; unverified_context: boolean };
    expect(memory.items.length).toBeGreaterThan(0);
    expect(memory.unverified_context).toBe(true);
    await navigate(page, `/chat?conversation=${conversation.conversation_id}`);
    await page
      .getByText("Hội thoại và ngữ cảnh (tùy chọn)", { exact: true })
      .click();
    await page.getByText("Lịch sử hội thoại (2)", { exact: true }).click();
    await expect(page.locator("main")).toContainText(question);
    await expect(
      page.getByRole("link", { name: "Xem lượt xử lý", exact: true }),
    ).toHaveCount(2);
    const cleared = responseFor(page, memoryPath, "DELETE", 204);
    await page
      .getByRole("button", { name: "Quên ngữ cảnh cũ", exact: true })
      .click();
    await cleared;
    const forgotten = (await (
      await page.request.get(memoryPath, { headers: auth })
    ).json()) as { items: unknown[] };
    expect(forgotten.items).toEqual([]);
    const history = (await (
      await page.request.get(
        `/api/v1/conversations/${conversation.conversation_id}/messages`,
        { headers: auth },
      )
    ).json()) as { total: number };
    expect(history.total).toBe(2);
    expect(modelRequests.get(page)).toEqual(["/api/v1/runs"]);
    await screenshot(page, "conversation-history.png");
  } finally {
    allowModel.set(page, false);
    if (token)
      await page.request.delete("/api/v1/sessions/me", {
        headers: { Authorization: `Bearer ${token}` },
      });
  }
});
