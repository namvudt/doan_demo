import { describe, expect, it, vi } from "vitest";
import { HttpApi } from "../src/api/http";
import type { HeritageView } from "../src/api/schema";
import { toHeritageDisplay } from "../src/ui/useHeritageCatalog";

const heritage: HeritageView = {
  heritage_id: "catalog-thap-rua",
  name: "Tháp Rùa",
  slug: "thap-rua",
  province: "Hà Nội",
  address: "Hồ Hoàn Kiếm",
  category: "monument",
  period: "Thế kỷ XIX",
  summary: "Hồ sơ được lưu trong cơ sở dữ liệu.",
  historical_information: "Thông tin lịch sử chưa xác minh.",
  cultural_information: "Thông tin văn hóa.",
  tags: ["Hồ Gươm"],
  location: {
    latitude: 21.028,
    longitude: 105.852,
    verification_status: "unverified",
    verification_note: "Cần kiểm chứng vị trí.",
    source_id: null,
  },
  media: [
    {
      media_id: "photo-1",
      kind: "image",
      url: "/api/v1/heritages/catalog-thap-rua/media/photo-1/content",
      alt: "Tháp Rùa trên hồ",
      caption: "Ảnh minh họa có ghi nguồn.",
      verified: false,
    },
  ],
  information_sources: [
    {
      source_id: "source-1",
      title: "Tư liệu tham khảo",
      publisher: "Nguồn tham khảo",
      url: "https://example.org/source",
      kind: "web",
      summary: "Chưa được lập chỉ mục RAG.",
      verified: false,
      verification_note: "Chưa xác minh.",
      index_status: "not_indexed",
    },
  ],
  content_status: "published",
  illustrative: true,
  version: 1,
  created_at: "2026-11-15T00:00:00Z",
  updated_at: "2026-11-15T00:00:00Z",
};

describe("persistent heritage catalog", () => {
  it("reads a public catalog with filters and resolves media against the API origin", async () => {
    const fetcher = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) => {
        void _input;
        void _init;
        return Response.json({
          items: [heritage],
          total: 1,
          limit: 500,
          offset: 0,
          has_more: false,
        });
      },
    );
    const api = new HttpApi({
      baseUrl: "https://backend.example/api/v1",
      accessToken: "guest-only",
      fetch: fetcher as typeof fetch,
    });
    const page = await api.heritages({
      q: "Tháp Rùa",
      province: "Hà Nội",
      has_location: true,
      limit: 500,
    });
    const [input, init] = fetcher.mock.calls[0];
    const url = new URL(String(input));
    expect(url.pathname).toBe("/api/v1/heritages");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      q: "Tháp Rùa",
      province: "Hà Nội",
      has_location: "true",
      limit: "500",
    });
    expect(new Headers(init?.headers).has("Authorization")).toBe(false);
    expect(page.items[0].heritage_id).toBe(heritage.heritage_id);
    expect(page.items[0].media[0].url).toBe(
      `https://backend.example${heritage.media[0].url}`,
    );
  });

  it("keeps opaque identity and unverified coordinates and source metadata", async () => {
    const fetcher = vi.fn(async (_input: string | URL | Request) => {
      void _input;
      return Response.json(heritage);
    });
    const api = new HttpApi({
      baseUrl: "https://backend.example/api/v1",
      fetch: fetcher as typeof fetch,
    });
    const record = await api.heritage(heritage.heritage_id);
    const display = toHeritageDisplay(record);
    expect(String(fetcher.mock.calls[0]?.[0])).toContain(
      "/heritages/catalog-thap-rua",
    );
    expect(display.id).toBe(heritage.heritage_id);
    expect(display.coordinates?.verified).toBe(false);
    expect(display.coordinateStatus).toBe("unverified");
    expect(display.illustrative).toBe(true);
    expect(record.information_sources[0].index_status).toBe("not_indexed");
  });

  it.each([
    "https://outside.example/api/v1/photo.png",
    "https://backend.example/other/photo.png",
  ])("rejects catalog media outside the configured API: %s", async (url) => {
    const api = new HttpApi({
      baseUrl: "https://backend.example/api/v1",
      fetch: async () =>
        Response.json({ ...heritage, media: [{ ...heritage.media[0], url }] }),
    });
    await expect(api.heritage(heritage.heritage_id)).rejects.toMatchObject({
      code: "UNSAFE_CATALOG_MEDIA_URL",
    });
  });

  it("imports a catalog photo as a guest-owned asset without creating a run", async () => {
    const asset = {
      asset_id: "22222222-2222-4222-8222-222222222222",
      sha256: "a".repeat(64),
      size_bytes: 100,
      width: 10,
      height: 10,
      media_type: "image/png",
      created_at: "2026-11-15T00:00:00Z",
      content_url:
        "/api/v1/assets/22222222-2222-4222-8222-222222222222/content",
    };
    const fetcher = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) => {
        void _input;
        void _init;
        return Response.json(asset, { status: 201 });
      },
    );
    const api = new HttpApi({
      baseUrl: "https://backend.example/api/v1",
      accessToken: "guest-only",
      fetch: fetcher as typeof fetch,
    });
    await expect(
      api.useHeritageMedia(heritage.heritage_id, "photo-1"),
    ).resolves.toMatchObject({ asset_id: asset.asset_id });
    expect(fetcher).toHaveBeenCalledTimes(1);
    const [input, init] = fetcher.mock.calls[0];
    expect(new URL(String(input)).pathname).toBe(
      "/api/v1/heritages/catalog-thap-rua/media/photo-1/assets",
    );
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("Authorization")).toBe(
      "Bearer guest-only",
    );
    const publicApi = new HttpApi({
      baseUrl: "https://backend.example/api/v1",
      fetch: fetcher as typeof fetch,
    });
    await expect(
      publicApi.useHeritageMedia(heritage.heritage_id, "photo-1"),
    ).rejects.toMatchObject({ code: "AUTH_REQUIRED" });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
