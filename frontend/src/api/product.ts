import { z } from "zod";
import { ApiError } from "./contracts";
import { errorResponseSchema, heritageViewSchema } from "./schema";

const date = z.string().datetime({ offset: true });
const uuid = z.string().uuid();
export const accountSchema = z
  .object({
    account_id: uuid,
    display_name: z.string(),
    email: z.string(),
    role: z.enum(["user", "editor", "admin"]),
    disabled: z.boolean(),
    version: z.number().int().positive(),
    created_at: date,
  })
  .strict();
export const accountAuthSchema = z
  .object({
    account: accountSchema,
    session_id: uuid,
    access_token: z.string().min(20),
    refresh_token: z.string().min(20),
    token_type: z.literal("bearer"),
    expires_at: date,
    refresh_expires_at: date,
  })
  .strict();
export const conversationSchema = z
  .object({
    conversation_id: uuid,
    title: z.string(),
    memory_enabled: z.boolean(),
    archived: z.boolean(),
    version: z.number().int().positive(),
    created_at: date,
    updated_at: date,
  })
  .strict();
export const conversationPageSchema = z
  .object({
    items: z.array(conversationSchema),
    total: z.number().int().nonnegative(),
    limit: z.number().int().positive(),
    offset: z.number().int().nonnegative(),
  })
  .strict();
export const messageSchema = z
  .object({
    message_id: uuid,
    turn_id: uuid,
    run_id: uuid,
    position: z.number().int().positive(),
    role: z.enum(["user", "assistant"]),
    content: z.string(),
    provenance: z.record(z.string(), z.unknown()),
    created_at: date,
  })
  .strict();
export const messagePageSchema = z
  .object({
    items: z.array(messageSchema),
    total: z.number().int().nonnegative(),
    limit: z.number().int().positive(),
    offset: z.number().int().nonnegative(),
  })
  .strict();
const favoriteSchema = z
  .object({
    heritage_id: z.string(),
    created_at: date,
    heritage: heritageViewSchema,
  })
  .strict();
export const favoritePageSchema = z
  .object({
    items: z.array(favoriteSchema),
    total: z.number().int().nonnegative(),
    limit: z.number().int().positive(),
    offset: z.number().int().nonnegative(),
  })
  .strict();
const registrationSchema = z
  .object({
    display_name: z.string().trim().min(1).max(80),
    email: z.string().trim().email().max(254),
    password: z.string().min(12).max(128),
  })
  .strict();

export type Account = z.infer<typeof accountSchema>;
export type AccountAuth = z.infer<typeof accountAuthSchema>;
export type Conversation = z.infer<typeof conversationSchema>;
export type ConversationMessage = z.infer<typeof messageSchema>;
export type HeritageFavorite = z.infer<typeof favoriteSchema>;

/** Product-only transport. It exposes no model-producing request or operations token. */
export class ProductApi {
  private readonly base: URL;
  private token?: string;
  constructor(
    baseUrl: string,
    private readonly fetcher: typeof fetch = globalThis.fetch.bind(globalThis),
  ) {
    const fallback =
      typeof document === "undefined" ? "http://localhost/" : document.baseURI;
    const base = new URL(baseUrl, fallback);
    if (
      !["http:", "https:"].includes(base.protocol) ||
      base.username ||
      base.password
    )
      throw new ApiError("API URL không hợp lệ.", 0, "INVALID_API_URL");
    base.search = "";
    base.hash = "";
    if (!base.pathname.endsWith("/")) base.pathname += "/";
    this.base = base;
  }
  setAccessToken(token?: string) {
    if (
      token &&
      [...token].some(
        (letter) => letter.charCodeAt(0) <= 32 || letter.charCodeAt(0) === 127,
      )
    )
      throw new ApiError("Token không hợp lệ.", 0, "INVALID_ACCESS_TOKEN");
    this.token = token || undefined;
  }
  private async request<T>(
    path: string,
    schema: z.ZodType<T>,
    options: {
      method?: string;
      body?: unknown;
      public?: boolean;
      signal?: AbortSignal;
    } = {},
  ): Promise<T> {
    const url = new URL(path, this.base);
    if (
      url.origin !== this.base.origin ||
      !url.pathname.startsWith(this.base.pathname)
    )
      throw new ApiError("Đường dẫn API không hợp lệ.", 0, "UNSAFE_API_URL");
    const headers = new Headers({ Accept: "application/json" });
    if (!options.public) {
      if (!this.token)
        throw new ApiError(
          "Hãy đăng nhập hoặc truy cập phiên khách.",
          401,
          "AUTH_REQUIRED",
        );
      headers.set("Authorization", `Bearer ${this.token}`);
    }
    if (options.body !== undefined)
      headers.set("Content-Type", "application/json");
    const controller = new AbortController();
    const abort = () => controller.abort();
    if (options.signal?.aborted) controller.abort();
    options.signal?.addEventListener("abort", abort, { once: true });
    const timer = setTimeout(abort, 15000);
    try {
      const response = await this.fetcher(url.toString(), {
        method: options.method || "GET",
        headers,
        body:
          options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal,
        credentials: "omit",
        redirect: "error",
      });
      const payload: unknown =
        response.status === 204
          ? undefined
          : await response.json().catch(() => null);
      if (!response.ok) {
        const failure = errorResponseSchema.safeParse(payload);
        throw new ApiError(
          failure.success
            ? failure.data.error.message
            : "Yêu cầu chưa hoàn tất.",
          response.status,
          failure.success ? failure.data.error.code : "PRODUCT_API_ERROR",
          undefined,
          response.headers.get("X-Request-ID") || undefined,
        );
      }
      const result = schema.safeParse(payload);
      if (!result.success)
        throw new ApiError(
          "Phản hồi chưa khớp hợp đồng API.",
          502,
          "INVALID_RESPONSE",
        );
      return result.data;
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener("abort", abort);
    }
  }
  register(displayName: string, email: string, password: string) {
    const body = registrationSchema.safeParse({
      display_name: displayName,
      email,
      password,
    });
    if (!body.success)
      throw new ApiError(
        "Hãy kiểm tra tên, email và mật khẩu tối thiểu 12 ký tự.",
        422,
        "INVALID_INPUT",
      );
    return this.request("accounts", accountSchema, {
      method: "POST",
      body: body.data,
      public: true,
    });
  }
  login(email: string, password: string) {
    return this.request("auth/sessions", accountAuthSchema, {
      method: "POST",
      body: { email, password },
      public: true,
    });
  }
  refresh(refreshToken: string) {
    return this.request("auth/refresh", accountAuthSchema, {
      method: "POST",
      body: { refresh_token: refreshToken },
      public: true,
    });
  }
  me(signal?: AbortSignal) {
    return this.request("users/me", accountSchema, { signal });
  }
  profile(displayName: string, version: number) {
    return this.request("users/me", accountSchema, {
      method: "PATCH",
      body: { display_name: displayName, version },
    });
  }
  conversations(signal?: AbortSignal) {
    return this.request("conversations?limit=100", conversationPageSchema, {
      signal,
    });
  }
  createConversation(title: string, memoryEnabled = false) {
    return this.request("conversations", conversationSchema, {
      method: "POST",
      body: { title, memory_enabled: memoryEnabled },
    });
  }
  conversation(id: string, signal?: AbortSignal) {
    return this.request(
      `conversations/${encodeURIComponent(id)}`,
      conversationSchema,
      { signal },
    );
  }
  messages(id: string, signal?: AbortSignal) {
    return this.request(
      `conversations/${encodeURIComponent(id)}/messages?limit=100`,
      messagePageSchema,
      { signal },
    );
  }
  clearMemory(id: string) {
    return this.request(
      `conversations/${encodeURIComponent(id)}/memory`,
      z.undefined(),
      { method: "DELETE" },
    );
  }
  favorites(signal?: AbortSignal) {
    return this.request(
      "users/me/heritage-favorites?limit=100",
      favoritePageSchema,
      { signal },
    );
  }
  favorite(id: string, saved: boolean) {
    const path = `users/me/heritage-favorites/${encodeURIComponent(id)}`;
    return saved
      ? this.request(path, favoriteSchema, { method: "PUT" })
      : this.request(path, z.undefined(), { method: "DELETE" });
  }
}
