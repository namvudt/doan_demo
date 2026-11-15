import { describe, expect, it } from "vitest";
import {
  PREVIEW_DEMO_ACCOUNTS,
  createPreviewInitialState,
} from "../src/preview/fixtures";
import {
  normalizePreviewEmail,
  throwIfPreviewInvalid,
  toPreviewSlug,
  validatePreviewContentSource,
  validatePreviewFeedback,
  validatePreviewHeritage,
  validatePreviewLogin,
  validatePreviewRegistration,
} from "../src/preview/validation";
import {
  PreviewValidationError,
  type PreviewHeritageInput,
} from "../src/preview/types";

const validHeritage: PreviewHeritageInput = {
  name: "Đình làng kiểm thử",
  province: "Hà Nội",
  address: "Một địa chỉ mô phỏng",
  category: "monument",
  introduction: "Nội dung đủ dài để kiểm tra hợp đồng biểu mẫu Preview.",
  coordinates: {
    latitude: 21.028,
    longitude: 105.852,
    verified: false,
    verificationNote: "Tọa độ minh họa chưa được backend xác minh.",
  },
  media: [
    {
      kind: "image",
      url: "/demo-thap-rua.jpg",
      alt: "Ảnh mô phỏng",
      caption: "Chỉ dùng trong UI Preview",
      verified: false,
    },
  ],
  sourceIds: ["preview-source-thap-rua-reference"],
};

describe("UI Preview fixture state", () => {
  it("is deterministic, deeply cloned and contains no password or token material", () => {
    const first = createPreviewInitialState();
    const second = createPreviewInitialState();

    expect(first).toEqual(second);
    expect(first).not.toBe(second);
    expect(first.heritages).not.toBe(second.heritages);
    first.heritages[0].name = "Đã thay đổi trong một bản sao";
    expect(second.heritages[0].name).toBe("Tháp Rùa");

    const serialized = JSON.stringify(second).toLocaleLowerCase("vi");
    expect(serialized).not.toContain("demo123!");
    expect(serialized).not.toContain("password");
    expect(serialized).not.toContain("access_token");
  });

  it("keeps stable IDs and every relation points to an existing record", () => {
    const state = createPreviewInitialState();
    const assertUnique = (values: string[]) =>
      expect(new Set(values).size).toBe(values.length);

    assertUnique(state.users.map((item) => item.id));
    assertUnique(state.heritages.map((item) => item.id));
    assertUnique(state.contentSources.map((item) => item.id));
    assertUnique(state.feedback.map((item) => item.id));

    const heritageIds = new Set(state.heritages.map((item) => item.id));
    const sourcesById = new Map(
      state.contentSources.map((source) => [source.id, source]),
    );
    for (const source of state.contentSources) {
      expect(heritageIds.has(source.heritageId)).toBe(true);
      expect(source.indexStatus).toBe("not_indexed");
      if (source.verified) expect(source.verificationNote).not.toBe("");
    }
    for (const heritage of state.heritages) {
      expect(heritage.illustrative).toBe(true);
      for (const sourceId of heritage.sourceIds) {
        expect(sourcesById.get(sourceId)?.heritageId).toBe(heritage.id);
      }
      if (heritage.coordinates) {
        expect(heritage.coordinates.verified).toBe(false);
        expect(heritage.coordinates.verificationNote).not.toBe("");
      }
      for (const media of heritage.media) {
        expect(media.url).toMatch(/^\/(?!\/)/);
        expect(media.verified).toBe(false);
      }
    }
    for (const favoriteIds of Object.values(
      state.favoriteHeritageIdsByIdentity,
    )) {
      expect(favoriteIds.every((id) => heritageIds.has(id))).toBe(true);
    }
  });

  it("maps every fictional demo account to an active fixture identity", () => {
    const state = createPreviewInitialState();
    for (const account of PREVIEW_DEMO_ACCOUNTS) {
      expect(
        state.users.find(
          (user) =>
            user.id === account.userId &&
            user.email === account.email &&
            user.role === account.role &&
            user.status === "active" &&
            user.fictional,
        ),
      ).toBeDefined();
    }
  });
});

describe("UI Preview validation", () => {
  it("normalizes Vietnamese email and creates stable accent-free slugs", () => {
    expect(normalizePreviewEmail("  USER@PREVIEW.LOCAL ")).toBe(
      "user@preview.local",
    );
    expect(toPreviewSlug("  Văn Miếu – Quốc Tử Giám  ")).toBe(
      "van-mieu-quoc-tu-giam",
    );
  });

  it("accepts valid registration/login input and reports field-level errors", () => {
    expect(
      validatePreviewRegistration({
        fullName: "Nguyễn An",
        email: "an@example.test",
        password: "Matkhau1",
        passwordConfirmation: "Matkhau1",
      }),
    ).toEqual({});
    expect(
      validatePreviewLogin({ email: "USER@PREVIEW.LOCAL", password: "x" }),
    ).toEqual({});

    expect(
      validatePreviewRegistration({
        fullName: "A",
        email: "không-hợp-lệ",
        password: "ngan",
        passwordConfirmation: "khác",
      }),
    ).toMatchObject({
      fullName: expect.any(String),
      email: expect.any(String),
      password: expect.any(String),
      passwordConfirmation: expect.any(String),
    });
    expect(validatePreviewLogin({ email: "x", password: "" })).toMatchObject({
      email: expect.any(String),
      password: expect.any(String),
    });
  });

  it("enforces coordinate provenance, bundled media and unique source links", () => {
    expect(validatePreviewHeritage(validHeritage)).toEqual({});
    expect(
      validatePreviewHeritage({
        ...validHeritage,
        coordinates: {
          latitude: 91,
          longitude: 181,
          verified: false,
          verificationNote: "",
        },
        media: [
          {
            kind: "image",
            url: "https://images.example.test/photo.jpg",
            alt: "external",
            caption: "external",
            verified: false,
          },
        ],
        sourceIds: ["same", "same"],
      }),
    ).toMatchObject({
      coordinates: expect.any(String),
      media: expect.any(String),
      sourceIds: expect.any(String),
    });
  });

  it("requires safe source URLs, verification notes and bounded feedback", () => {
    expect(
      validatePreviewContentSource({
        heritageId: "preview-heritage-thap-rua",
        title: "Nguồn kiểm thử",
        publisher: "Đơn vị kiểm thử",
        url: "https://example.test/reference",
        kind: "reference",
        verified: true,
        verificationNote: "Đã đối chiếu metadata thủ công.",
      }),
    ).toEqual({});
    expect(
      validatePreviewContentSource({
        heritageId: "",
        title: "x",
        publisher: "x",
        url: "https://user:secret@example.test/reference",
        kind: "reference",
        verified: true,
        verificationNote: "",
      }),
    ).toMatchObject({
      heritageId: expect.any(String),
      title: expect.any(String),
      publisher: expect.any(String),
      url: expect.any(String),
      verificationNote: expect.any(String),
    });
    expect(
      validatePreviewFeedback({
        runId: "",
        rating: "needs_review",
        note: "x".repeat(1501),
      }),
    ).toMatchObject({ runId: expect.any(String), note: expect.any(String) });
  });

  it("throws the typed validation error consumed by forms", () => {
    expect(() =>
      throwIfPreviewInvalid({ name: "Tên không hợp lệ" }, "Không thể lưu"),
    ).toThrowError(PreviewValidationError);
    try {
      throwIfPreviewInvalid({ name: "Tên không hợp lệ" }, "Không thể lưu");
    } catch (error) {
      expect(error).toMatchObject({
        code: "PREVIEW_VALIDATION_ERROR",
        fields: { name: "Tên không hợp lệ" },
      });
    }
  });
});
