import { describe, expect, it, vi } from "vitest";
import { ProductApi, accountSchema } from "../src/api/product";
import { runCreateSchema } from "../src/api/schema";

const ID = "11111111-1111-4111-8111-111111111111";
const NOW = "2026-11-16T00:00:00Z";
const account = {
  account_id: ID,
  display_name: "Người dùng",
  email: "user@example.test",
  role: "user",
  disabled: false,
  version: 1,
  created_at: NOW,
};
const issued = {
  account,
  session_id: ID,
  access_token: "access-fixture-token-01234567890",
  refresh_token: "refresh-fixture-token-01234567890",
  token_type: "bearer",
  expires_at: NOW,
  refresh_expires_at: NOW,
};
const conversation = {
  conversation_id: ID,
  title: "Hội thoại",
  memory_enabled: false,
  archived: false,
  version: 1,
  created_at: NOW,
  updated_at: NOW,
};

describe("product transport", () => {
  it("keeps registration public and never sends client-selected roles", async () => {
    const fetcher = vi.fn(async () => Response.json(account));
    const api = new ProductApi("https://api.example.test/api/v1", fetcher);
    await api.register(
      " Tên mới ",
      "user@example.test",
      "Long-test-password-0123",
    );
    const [url, init] = fetcher.mock.calls[0]! as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("https://api.example.test/api/v1/accounts");
    expect(new Headers(init.headers).has("Authorization")).toBe(false);
    expect(JSON.parse(String(init.body))).toEqual({
      display_name: "Tên mới",
      email: "user@example.test",
      password: "Long-test-password-0123",
    });
    expect(init.credentials).toBe("omit");
    expect(init.redirect).toBe("error");
    expect(() => api.register("Name", "user@example.test", "short")).toThrow();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("reads issued account sessions strictly and rotates via the public refresh endpoint", async () => {
    const fetcher = vi.fn(async () => Response.json(issued));
    const api = new ProductApi("https://api.example.test/api/v1", fetcher);
    const signed = await api.login(account.email, "Long-test-password-0123");
    api.setAccessToken(signed.access_token);
    await api.refresh(signed.refresh_token);
    const [url, init] = fetcher.mock.calls[1]! as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toMatch(/\/auth\/refresh$/);
    expect(new Headers(init.headers).has("Authorization")).toBe(false);
    expect(JSON.parse(String(init.body))).toEqual({
      refresh_token: signed.refresh_token,
    });
    expect(
      accountSchema.safeParse({ ...account, password_hash: "hidden" }).success,
    ).toBe(false);
  });
  it("requires authentication for owned data and forgets credentials explicitly", async () => {
    const fetcher = vi.fn(async () =>
      Response.json({ items: [], total: 0, limit: 100, offset: 0 }),
    );
    const api = new ProductApi("https://api.example.test/api/v1", fetcher);
    await expect(api.favorites()).rejects.toMatchObject({
      status: 401,
      code: "AUTH_REQUIRED",
    });
    expect(fetcher).not.toHaveBeenCalled();
    api.setAccessToken(issued.access_token);
    await api.favorites();
    const init = (
      fetcher.mock.calls[0]! as unknown as [string, RequestInit]
    )[1];
    expect(new Headers(init.headers).get("Authorization")).toBe(
      `Bearer ${issued.access_token}`,
    );
    api.setAccessToken(undefined);
    await expect(api.conversations()).rejects.toMatchObject({
      code: "AUTH_REQUIRED",
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("creates an explicitly selected memory policy without producing an AI run", async () => {
    const fetcher = vi.fn(async () => Response.json(conversation));
    const api = new ProductApi("https://api.example.test/api/v1", fetcher);
    api.setAccessToken(issued.access_token);
    expect(fetcher).not.toHaveBeenCalled();
    await api.createConversation("Hội thoại");
    const [url, init] = fetcher.mock.calls[0]! as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toMatch(/\/conversations$/);
    expect(JSON.parse(String(init.body))).toEqual({
      title: "Hội thoại",
      memory_enabled: false,
    });
  });
  it("keeps profile version conflicts and ownership errors visible", async () => {
    const fetcher = vi.fn(async () =>
      Response.json(
        {
          error: {
            code: "account_version_conflict",
            message: "Reload profile",
            request_id: "fixture",
          },
        },
        { status: 409 },
      ),
    );
    const api = new ProductApi("https://api.example.test/api/v1", fetcher);
    api.setAccessToken(issued.access_token);
    await expect(api.profile("New name", 1)).rejects.toMatchObject({
      status: 409,
      code: "account_version_conflict",
    });
    const init = (
      fetcher.mock.calls[0]! as unknown as [string, RequestInit]
    )[1];
    expect(JSON.parse(String(init.body))).toEqual({
      display_name: "New name",
      version: 1,
    });
  });
  it("rejects unsafe connection credentials and token control characters", () => {
    expect(
      () => new ProductApi("https://user:secret@api.example.test/api/v1"),
    ).toThrow();
    const api = new ProductApi("https://api.example.test/api/v1");
    expect(() => api.setAccessToken("token\ninvalid")).toThrow();
  });
  it("accepts structured conversation/catalog context while keeping legacy run bodies valid", () => {
    const body = { asset_id: ID, question: "Câu hỏi" };
    expect(runCreateSchema.safeParse(body).success).toBe(true);
    expect(
      runCreateSchema.safeParse({
        ...body,
        conversation_id: ID,
        heritage_id: "preview-heritage-van-mieu",
      }).success,
    ).toBe(true);
    expect(
      runCreateSchema.safeParse({ ...body, conversation_id: "not-a-uuid" })
        .success,
    ).toBe(false);
  });
});
