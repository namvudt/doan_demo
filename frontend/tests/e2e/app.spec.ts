import { expect, test, type Page } from "@playwright/test";

const DEMO_PASSWORD = "Demo123!";

async function login(
  page: Page,
  email: "user@preview.local" | "admin@preview.local" = "user@preview.local",
) {
  await page.goto("/login");
  await page.getByLabel("Email mô phỏng").fill(email);
  await page.getByLabel("Mật khẩu mô phỏng").fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập Preview" }).click();
  await expect(page).toHaveURL(/\/chat$/);
  await expect(page.getByRole("status")).toContainText("UI Preview");
  await page.locator('.main-nav a[href="/heritages"]').click();
  await expect(page).toHaveURL(/\/heritages$/);
}

async function navigateInApp(page: Page, path: string) {
  await page.evaluate((nextPath) => {
    window.history.pushState(null, "", nextPath);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);
}

test.beforeEach(async ({ page }) => {
  // Preview E2E is hermetic: only the local Vite origin may be requested.
  await page.route(/^https?:\/\//, async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname === "127.0.0.1" || url.hostname === "localhost") {
      await route.continue();
    } else {
      await route.abort("blockedbyclient");
    }
  });
});

test("protected Preview routes return to the intended page after login", async ({
  page,
}) => {
  await page.goto("/favorites");
  await expect(page).toHaveURL(/\/login$/);
  await expect(
    page.getByRole("heading", { name: "Chào mừng trở lại" }),
  ).toBeVisible();

  await page.getByLabel("Email mô phỏng").fill("user@preview.local");
  await page.getByLabel("Mật khẩu mô phỏng").fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập Preview" }).click();

  await expect(page).toHaveURL(/\/favorites$/);
  await expect(
    page.getByRole("heading", { name: "Những điều bạn muốn quay lại" }),
  ).toBeVisible();
  await expect(
    page.getByText("Nguyễn Minh Anh", { exact: true }),
  ).toBeVisible();
});

test("catalog, detail, favorites and map share one Preview identity", async ({
  page,
}) => {
  await login(page);
  const search = page.getByPlaceholder("Tìm theo tên, địa phương, từ khóa…");
  await search.fill("Văn Miếu");
  await expect(page.locator(".heritage-card")).toHaveCount(1);
  await page.getByRole("heading", { name: "Văn Miếu – Quốc Tử Giám" }).click();

  await expect(page).toHaveURL(/\/heritages\/preview-heritage-van-mieu$/);
  await expect(
    page.getByRole("heading", { name: "Văn Miếu – Quốc Tử Giám", level: 1 }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Yêu thích", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Đã yêu thích", exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Mở trên bản đồ" }).click();
  await expect(page).toHaveURL(/\/map\?selected=preview-heritage-van-mieu$/);
  await expect(
    page.getByRole("heading", { name: "Văn Miếu – Quốc Tử Giám", level: 2 }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Xem hồ sơ" })).toBeVisible();

  await page.locator('.main-nav a[href="/favorites"]').click();
  const savedItem = page.locator(".saved-list article").filter({
    hasText: "Văn Miếu – Quốc Tử Giám",
  });
  await expect(savedItem).toBeVisible();
  await savedItem.getByRole("button", { name: "Bỏ lưu" }).click();
  await expect(savedItem).toHaveCount(0);
});

test("admin CRUD immediately updates the public catalog and map", async ({
  page,
}) => {
  const initialName = "Di sản kiểm thử E2E";
  const updatedName = "Di sản E2E đã cập nhật";
  await login(page, "admin@preview.local");
  await page.locator('a[href="/admin/heritages"]').first().click();
  await expect(page).toHaveURL(/\/admin\/heritages$/);

  await page.getByRole("button", { name: "Thêm di sản" }).click();
  const createDialog = page.getByRole("dialog");
  await createDialog.getByLabel("Tên di sản").fill(initialName);
  await createDialog.getByLabel("Tỉnh/thành").fill("Hà Nội");
  await createDialog.getByLabel("Địa chỉ").fill("Địa chỉ mô phỏng E2E");
  await createDialog.getByLabel("Xuất bản").selectOption("published");
  await createDialog
    .getByLabel("Giới thiệu")
    .fill("Hồ sơ dùng để kiểm tra catalog dùng chung trong UI Preview.");
  await createDialog.getByLabel("Kinh độ").fill("105.851");
  await createDialog.getByRole("button", { name: "Tạo hồ sơ" }).click();
  await expect(createDialog).toBeVisible();
  await expect(
    createDialog
      .getByText("Hãy nhập đủ cả vĩ độ và kinh độ, hoặc để trống cả hai.", {
        exact: true,
      })
      .first(),
  ).toBeVisible();
  await createDialog.getByRole("textbox", { name: /^Vĩ độ/ }).fill("21.031");
  await createDialog.getByRole("button", { name: "Tạo hồ sơ" }).click();
  await expect(createDialog).toHaveCount(0);
  await expect(
    page.getByRole("row").filter({ hasText: initialName }),
  ).toBeVisible();

  await page.locator('.main-nav a[href="/heritages"]').click();
  await page
    .getByPlaceholder("Tìm theo tên, địa phương, từ khóa…")
    .fill(initialName);
  await expect(page.getByRole("heading", { name: initialName })).toBeVisible();

  await page.locator('.main-nav a[href="/map"]').click();
  await page.getByPlaceholder("Tên hoặc địa phương…").fill(initialName);
  await page
    .locator(".map-results")
    .getByRole("button", { name: new RegExp(initialName) })
    .click();
  await expect(
    page.getByRole("heading", { name: initialName, level: 2 }),
  ).toBeVisible();

  await page.locator('a[href="/admin/heritages"]').first().click();
  const createdRow = page.getByRole("row").filter({ hasText: initialName });
  await createdRow.getByRole("button", { name: `Sửa ${initialName}` }).click();
  const editDialog = page.getByRole("dialog");
  await editDialog.getByLabel("Tên di sản").fill(updatedName);
  await editDialog.getByRole("button", { name: "Lưu thay đổi" }).click();
  await expect(
    page.getByRole("row").filter({ hasText: updatedName }),
  ).toBeVisible();

  await page.locator('.main-nav a[href="/heritages"]').click();
  await page
    .getByPlaceholder("Tìm theo tên, địa phương, từ khóa…")
    .fill(updatedName);
  await expect(page.getByRole("heading", { name: updatedName })).toBeVisible();

  await page.locator('a[href="/admin/heritages"]').first().click();
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("row")
    .filter({ hasText: updatedName })
    .getByRole("button", { name: `Xóa ${updatedName}` })
    .click();
  await expect(
    page.getByRole("row").filter({ hasText: updatedName }),
  ).toHaveCount(0);

  await page.locator('.main-nav a[href="/heritages"]').click();
  await page
    .getByPlaceholder("Tìm theo tên, địa phương, từ khóa…")
    .fill(updatedName);
  await expect(
    page.getByText("Không có kết quả phù hợp", { exact: true }),
  ).toBeVisible();
});

test("non-admin users see forbidden and unknown paths render 404", async ({
  page,
}) => {
  await login(page);
  await navigateInApp(page, "/admin");
  await expect(page).toHaveURL(/\/forbidden$/);
  await expect(
    page.getByText("Bạn không có quyền mở trang này", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Cần vai trò quản trị viên", { exact: false }),
  ).toBeVisible();

  await navigateInApp(page, "/duong-dan-khong-ton-tai");
  await expect(page).toHaveURL(/\/duong-dan-khong-ton-tai$/);
  await expect(
    page.getByText("Không tìm thấy trang", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("404", { exact: true })).toBeVisible();
});

test("all published heritage photos load locally and a failed photo can recover", async ({
  page,
}) => {
  await page.goto("/heritages");
  const cards = page.locator(".heritage-card");
  await expect(cards).toHaveCount(7);
  for (const card of await cards.all()) {
    await card.scrollIntoViewIfNeeded();
    const photo = card.locator("img");
    await expect(photo).toBeVisible();
    await expect
      .poll(() =>
        photo.evaluate((element) => {
          const image = element as HTMLImageElement;
          return image.complete && image.naturalWidth > 0;
        }),
      )
      .toBe(true);
    expect(
      new URL((await photo.getAttribute("src")) || "", page.url()).origin,
    ).toBe(new URL(page.url()).origin);
  }

  await page.route("**/demo-thap-rua.jpg*", async (route) => {
    if (new URL(route.request().url()).searchParams.has("image-retry")) {
      await route.continue();
    } else {
      await route.abort("failed");
    }
  });
  await page.goto("/heritages/preview-heritage-thap-rua");
  await expect(page.locator(".detail-image .image-fallback")).toBeVisible();
  await page.getByRole("button", { name: "Thử tải lại ảnh" }).click();
  await expect
    .poll(() =>
      page.locator(".detail-image img").evaluate((element) => {
        const image = element as HTMLImageElement;
        return image.complete && image.naturalWidth > 0;
      }),
    )
    .toBe(true);
  await expect(page.locator(".detail-image .image-fallback")).toHaveCount(0);
});

test("catalog tag search and the offline map keep selection and filters in sync", async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto("/heritages");
  await page
    .getByPlaceholder("Tìm theo tên, địa phương, từ khóa…")
    .fill(" Giáo dục ");
  await expect(page.locator(".heritage-card")).toHaveCount(1);
  await page.getByRole("link", { name: "Xem bản đồ", exact: true }).click();
  await expect(page.locator(".map-result")).toHaveCount(1);
  await expect(
    page.getByRole("heading", { name: "Văn Miếu – Quốc Tử Giám", level: 2 }),
  ).toBeVisible();
  await expect(page.getByTestId("offline-map")).toBeVisible();
  await expect(page.locator(".map-result")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page
    .getByRole("button", { name: "Chọn Văn Miếu – Quốc Tử Giám trên sơ đồ" })
    .click();
  await expect(page).toHaveURL(/selected=preview-heritage-van-mieu/);

  await page.getByPlaceholder("Tên hoặc địa phương…").fill("");
  await expect(page.locator(".map-result")).toHaveCount(7);
  await page
    .locator(".map-results")
    .getByRole("button", { name: /Đô thị cổ Hội An/ })
    .click();
  await expect(
    page.getByRole("heading", { name: "Đô thị cổ Hội An", level: 2 }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Chọn Đô thị cổ Hội An trên sơ đồ" }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByLabel("Lọc địa phương").selectOption("Hà Nội");
  await expect(page.locator(".map-result")).toHaveCount(4);
  await page
    .getByRole("button", { name: "Chỉ danh sách", exact: true })
    .click();
  await expect(page.getByTestId("offline-map")).toHaveCount(0);
  await expect(page.locator(".map-results")).toBeVisible();
  await page.getByRole("button", { name: "Hiện bản đồ", exact: true }).click();
  await expect(page.getByTestId("offline-map")).toBeVisible();

  // Exercise disposal while Leaflet is still changing its selected view.
  await page.getByRole("button", { name: "Chọn Tháp Rùa trên sơ đồ" }).click();
  await page
    .getByRole("button", { name: "Chỉ danh sách", exact: true })
    .click();
  await page.getByRole("button", { name: "Hiện bản đồ", exact: true }).click();
  await page.getByLabel("Lọc loại hình").selectOption("temple");
  await page
    .getByRole("button", { name: "Chọn Văn Miếu – Quốc Tử Giám trên sơ đồ" })
    .click();
  await page.locator('.main-nav a[href="/heritages"]').click();
  await expect(page.locator(".map-canvas")).toHaveCount(0);
  await expect(page.locator(".heritage-grid")).toBeVisible();
  // Leaflet's CSS zoom completion uses a delayed timer. Keep observing after
  // unmount so a dangling callback cannot silently pass at the end of the test.
  await page.waitForTimeout(400);
  expect(pageErrors).toEqual([]);
});

test("@mobile navigation and catalog/map layouts fit a narrow viewport", async ({
  page,
}) => {
  await page.goto("/heritages");
  await expect(
    page.getByRole("heading", { name: "Những địa điểm, những lớp thời gian" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Mở điều hướng" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);

  await page.getByRole("button", { name: "Mở điều hướng" }).click();
  await page
    .getByRole("navigation", { name: "Điều hướng chính" })
    .getByRole("link", { name: "Bản đồ" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Khám phá theo địa điểm" }),
  ).toBeVisible();
  await expect(page.locator(".map-canvas")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
