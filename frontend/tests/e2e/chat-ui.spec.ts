import { expect, test, type Page } from "@playwright/test";

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=",
  "base64",
);
const attachment = {
  name: "heritage-chat-test.png",
  mimeType: "image/png",
  buffer: PNG,
};

type Traffic = { documents: number; errors: string[]; backendPaths: string[] };

async function isolatePreview(page: Page): Promise<Traffic> {
  const traffic: Traffic = { documents: 0, errors: [], backendPaths: [] };
  page.on("pageerror", (error) => traffic.errors.push(error.message));
  page.on("request", (request) => {
    if (request.resourceType() === "document") traffic.documents += 1;
  });
  await page.route(/^https?:\/\//, async (route) => {
    const url = new URL(route.request().url());
    if (
      url.pathname.startsWith("/api/") ||
      url.pathname.startsWith("/health/")
    ) {
      traffic.backendPaths.push(url.pathname);
      await route.abort("blockedbyclient");
    } else if (["127.0.0.1", "localhost"].includes(url.hostname)) {
      await route.continue();
    } else {
      await route.abort("blockedbyclient");
    }
  });
  return traffic;
}

function questionField(page: Page) {
  return page.getByRole("textbox", { name: /Bạn muốn tìm hiểu điều gì/ });
}

function submitButton(page: Page) {
  return page.getByRole("button", { name: "Khám phá", exact: true });
}

async function assertPreviewOnly(traffic: Traffic) {
  expect(traffic.backendPaths).toEqual([]);
  expect(traffic.errors).toEqual([]);
}

async function assertNoHorizontalOverflow(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
}

test("desktop composer keeps the main action in view and edits attachments without losing the question", async ({
  page,
}) => {
  const traffic = await isolatePreview(page);
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto("/chat");
  await expect(questionField(page)).toBeVisible();
  await expect(submitButton(page)).toBeDisabled();
  const action = await submitButton(page).boundingBox();
  expect(action).not.toBeNull();
  expect(action!.height).toBeGreaterThanOrEqual(44);
  expect(action!.y + action!.height).toBeLessThanOrEqual(768);

  const suggestion = "Thông tin nào cần kiểm chứng thêm?";
  await page.getByRole("button", { name: suggestion, exact: true }).click();
  await expect(questionField(page)).toHaveValue(suggestion);
  await expect(submitButton(page)).toBeEnabled();

  const input = page.getByLabel("Chọn ảnh để hỏi", { exact: true });
  await input.setInputFiles(attachment);
  const preview = page.getByRole("img", {
    name: "Ảnh đã chọn để hỏi",
    exact: true,
  });
  await expect(preview).toBeVisible();
  await expect(page.getByText(attachment.name, { exact: true })).toBeVisible();
  const originalSource = await preview.getAttribute("src");
  await input.setInputFiles({
    name: "not-an-image.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("plain text"),
  });
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(preview).toHaveAttribute("src", originalSource || "");
  await expect(questionField(page)).toHaveValue(suggestion);

  await page
    .getByRole("button", { name: "Bỏ ảnh đã chọn", exact: true })
    .click();
  await expect(preview).toHaveCount(0);
  await expect(questionField(page)).toHaveValue(suggestion);
  await input.setInputFiles(attachment);
  await expect(preview).toBeVisible();
  await expect(questionField(page)).toHaveValue(suggestion);
  await assertNoHorizontalOverflow(page);
  expect(traffic.documents).toBe(1);
  await assertPreviewOnly(traffic);
});

test("dropping an image updates the attachment and a blank question cannot be submitted", async ({
  page,
}) => {
  const traffic = await isolatePreview(page);
  await page.goto("/chat");
  await expect(questionField(page)).toBeVisible();
  const transfer = await page.evaluateHandle(
    (bytes) => {
      const dataTransfer = new DataTransfer();
      dataTransfer.items.add(
        new File([new Uint8Array(bytes)], "dropped-heritage.png", {
          type: "image/png",
        }),
      );
      return dataTransfer;
    },
    [...PNG],
  );
  try {
    await page
      .getByTestId("chat-image-dropzone")
      .dispatchEvent("drop", { dataTransfer: transfer });
  } finally {
    await transfer.dispose();
  }
  await expect(
    page.getByText("dropped-heritage.png", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "Ảnh đã chọn để hỏi", exact: true }),
  ).toBeVisible();
  await questionField(page).fill("   ");
  await expect(submitButton(page)).toBeDisabled();
  await expect(questionField(page)).toHaveAttribute("maxlength", "4000");
  await questionField(page).fill(
    "Các chi tiết nào có thể quan sát trong bức ảnh?",
  );
  await expect(submitButton(page)).toBeEnabled();
  expect(traffic.documents).toBe(1);
  await assertPreviewOnly(traffic);
});

test("Preview answers retain source context and reveal processing details only on demand", async ({
  page,
}) => {
  const traffic = await isolatePreview(page);
  await page.goto("/chat?heritage=preview-heritage-thap-rua");
  await expect(questionField(page)).toHaveValue(/Tháp Rùa/);
  const question = await questionField(page).inputValue();
  await submitButton(page).click();
  await expect(page).toHaveURL(/\/chat\/runs\/preview-/);
  const resultUrl = page.url();
  await expect(page.locator(".answer-card")).toBeVisible();
  await expect(page.locator(".answer-card")).toContainText("Kết quả mô phỏng");
  await expect(page.locator(".answer-card")).toContainText(
    "không phải phân tích AI thật",
  );
  await expect(
    page
      .locator(".sources-section")
      .getByRole("link", { name: "Tư liệu tham khảo về Tháp Rùa" }),
  ).toHaveAttribute("href", /^https:\/\//);
  await expect(page.locator(".sources-section")).toContainText(
    "TƯ LIỆU MINH HỌA",
  );
  await expect(page.locator(".sources-section")).toContainText(
    "Metadata hồ sơ Preview",
  );

  const processing = page.locator(".execution-details").first();
  await expect(processing).toBeVisible();
  expect(
    await processing.evaluate(
      (element) => (element as HTMLDetailsElement).open,
    ),
  ).toBe(false);
  await processing.locator("summary").click();
  expect(
    await processing.evaluate(
      (element) => (element as HTMLDetailsElement).open,
    ),
  ).toBe(true);
  await expect(processing).toContainText("Kiểm tra đầu vào");
  await processing.locator("summary").click();
  expect(
    await processing.evaluate(
      (element) => (element as HTMLDetailsElement).open,
    ),
  ).toBe(false);
  await expect(page.locator(".answer-card")).toContainText("Tháp Rùa");

  await page.getByRole("link", { name: "Câu hỏi mới", exact: true }).click();
  await expect(page).toHaveURL(/\/chat(?:\?.*)?$/);
  await page.getByRole("button", { name: "Mở lịch sử", exact: true }).click();
  const history = page.locator("#chat-history-panel");
  await expect(history).toBeVisible();
  await history.getByRole("link", { name: question }).click();
  await expect(page).toHaveURL(resultUrl);
  await expect(page.locator(".answer-card")).toContainText("Tháp Rùa");
  expect(traffic.documents).toBe(1);
  await assertPreviewOnly(traffic);
});

test("history can be opened and closed without clearing a draft", async ({
  page,
}) => {
  const traffic = await isolatePreview(page);
  await page.goto("/chat");
  const draft = "Kiến trúc này có những điểm gì cần đối chiếu thêm?";
  await questionField(page).fill(draft);
  await page.getByRole("button", { name: "Mở lịch sử", exact: true }).click();
  await expect(page.locator("#chat-history-panel")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Đóng lịch sử", exact: true }).first(),
  ).toHaveAttribute("aria-expanded", "true");
  await page
    .getByRole("button", { name: "Đóng bảng lịch sử", exact: true })
    .click();
  await expect(page.locator("#chat-history-panel")).toBeHidden();
  await expect(questionField(page)).toHaveValue(draft);
  await page.getByRole("button", { name: "Mở lịch sử", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Đóng bảng lịch sử", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.locator("#chat-history-panel")).toBeHidden();
  await expect(
    page.getByRole("button", { name: "Mở lịch sử", exact: true }),
  ).toBeFocused();
  await expect(questionField(page)).toHaveValue(draft);
  expect(traffic.documents).toBe(1);
  await assertPreviewOnly(traffic);
});

test("@mobile composer, history and answer remain usable at 390px and 320px", async ({
  page,
}) => {
  const traffic = await isolatePreview(page);
  for (const viewport of [
    { width: 390, height: 844 },
    { width: 320, height: 700 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/chat");
    await expect(questionField(page)).toBeVisible();
    await assertNoHorizontalOverflow(page);
    await page.getByRole("button", { name: "Mở lịch sử", exact: true }).click();
    const history = page.locator("#chat-history-panel");
    await expect(history).toBeVisible();
    const panel = await history.boundingBox();
    expect(panel).not.toBeNull();
    expect(panel!.x).toBeGreaterThanOrEqual(0);
    expect(panel!.x + panel!.width).toBeLessThanOrEqual(viewport.width + 1);
    expect(panel!.y + panel!.height).toBeLessThanOrEqual(viewport.height + 1);
    await page
      .getByRole("button", { name: "Đóng bảng lịch sử", exact: true })
      .click();
    await questionField(page).fill(
      "Ảnh này có chi tiết kiến trúc nào đáng chú ý?",
    );
    await submitButton(page).scrollIntoViewIfNeeded();
    await expect(submitButton(page)).toBeVisible();
    await submitButton(page).click();
    await expect(page.locator(".answer-card")).toBeVisible();
    await assertNoHorizontalOverflow(page);
    const processing = page.locator(".execution-details").first();
    await processing.locator("summary").click();
    await expect(processing).toContainText("Kiểm tra đầu vào");
    await assertNoHorizontalOverflow(page);
  }
  await assertPreviewOnly(traffic);
});
