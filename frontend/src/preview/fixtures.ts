import type {
  PreviewContentSource,
  PreviewFeedback,
  PreviewHeritage,
  PreviewRole,
  PreviewState,
  PreviewUser,
} from "./types";

const FIXTURE_TIME = "2026-11-15T00:00:00.000Z";

export const PREVIEW_GUEST_IDENTITY = "preview-anonymous-guest";

export const PREVIEW_ROLE_USER_IDS: Record<PreviewRole, string> = {
  guest: "preview-user-guest",
  user: "preview-user-member",
  admin: "preview-user-admin",
};

/** Fictional credentials intended only for the visibly labelled UI Preview. */
export const PREVIEW_DEMO_ACCOUNTS = [
  {
    userId: PREVIEW_ROLE_USER_IDS.guest,
    email: "guest@preview.local",
    password: "Demo123!",
    role: "guest" as const,
  },
  {
    userId: PREVIEW_ROLE_USER_IDS.user,
    email: "user@preview.local",
    password: "Demo123!",
    role: "user" as const,
  },
  {
    userId: PREVIEW_ROLE_USER_IDS.admin,
    email: "admin@preview.local",
    password: "Demo123!",
    role: "admin" as const,
  },
] as const;

export const previewUsers: PreviewUser[] = [
  {
    id: PREVIEW_ROLE_USER_IDS.guest,
    fullName: "Khách tham quan",
    email: PREVIEW_DEMO_ACCOUNTS[0].email,
    role: "guest",
    status: "active",
    fictional: true,
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
  },
  {
    id: PREVIEW_ROLE_USER_IDS.user,
    fullName: "Nguyễn Minh Anh",
    email: PREVIEW_DEMO_ACCOUNTS[1].email,
    role: "user",
    status: "active",
    fictional: true,
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
  },
  {
    id: PREVIEW_ROLE_USER_IDS.admin,
    fullName: "Trần Quản Trị",
    email: PREVIEW_DEMO_ACCOUNTS[2].email,
    role: "admin",
    status: "active",
    fictional: true,
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
  },
  {
    id: "preview-user-suspended",
    fullName: "Lê Tài Khoản Tạm Khóa",
    email: "tamkhoa@preview.example.test",
    role: "user",
    status: "suspended",
    fictional: true,
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
  },
];

export const previewContentSources: PreviewContentSource[] = [
  {
    id: "preview-source-thap-rua-reference",
    heritageId: "preview-heritage-thap-rua",
    title: "Tư liệu tham khảo về Tháp Rùa",
    publisher: "Wikipedia tiếng Việt",
    url: "https://vi.wikipedia.org/wiki/Th%C3%A1p_R%C3%B9a",
    kind: "reference",
    summary:
      "Liên kết tham khảo cho bố cục UI; nội dung chưa được kiểm chứng trong phiên Preview.",
    verified: false,
    verificationNote:
      "Chưa qua quy trình biên tập và đối chiếu nguồn của ứng dụng.",
    indexStatus: "not_indexed",
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
  },
  {
    id: "preview-source-hoang-thanh-unesco",
    heritageId: "preview-heritage-hoang-thanh",
    title: "Central Sector of the Imperial Citadel of Thang Long",
    publisher: "UNESCO World Heritage Centre",
    url: "https://whc.unesco.org/en/list/1328/",
    kind: "unesco",
    summary:
      "Trang danh mục UNESCO dùng làm nguồn metadata minh họa cho hồ sơ.",
    verified: true,
    verificationNote:
      "Đã đối chiếu loại và URL nguồn trong bộ fixture; không đồng nghĩa toàn bộ diễn giải đã được thẩm định.",
    indexStatus: "not_indexed",
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
  },
  {
    id: "preview-source-hue-unesco",
    heritageId: "preview-heritage-co-do-hue",
    title: "Complex of Hué Monuments",
    publisher: "UNESCO World Heritage Centre",
    url: "https://whc.unesco.org/en/list/678/",
    kind: "unesco",
    summary: "Nguồn danh mục chính thức được gắn với hồ sơ minh họa.",
    verified: true,
    verificationNote:
      "Đã đối chiếu loại và URL nguồn; nội dung Preview vẫn là dữ liệu mô phỏng.",
    indexStatus: "not_indexed",
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
  },
  {
    id: "preview-source-hoi-an-unesco",
    heritageId: "preview-heritage-hoi-an",
    title: "Hoi An Ancient Town",
    publisher: "UNESCO World Heritage Centre",
    url: "https://whc.unesco.org/en/list/948/",
    kind: "unesco",
    summary: "Nguồn metadata minh họa cho hồ sơ Đô thị cổ Hội An.",
    verified: true,
    verificationNote:
      "Đã đối chiếu loại và URL nguồn; chưa phải bằng chứng RAG đã truy xuất.",
    indexStatus: "not_indexed",
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
  },
  {
    id: "preview-source-my-son-unesco",
    heritageId: "preview-heritage-my-son",
    title: "My Son Sanctuary",
    publisher: "UNESCO World Heritage Centre",
    url: "https://whc.unesco.org/en/list/949/",
    kind: "unesco",
    summary: "Nguồn metadata minh họa cho hồ sơ Thánh địa Mỹ Sơn.",
    verified: true,
    verificationNote:
      "Đã đối chiếu loại và URL nguồn; chưa phải bằng chứng RAG đã truy xuất.",
    indexStatus: "not_indexed",
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
  },
  {
    id: "preview-source-museum-official",
    heritageId: "preview-heritage-bao-tang-lich-su",
    title: "Bảo tàng Lịch sử Quốc gia",
    publisher: "Bảo tàng Lịch sử Quốc gia",
    url: "https://baotanglichsu.vn/",
    kind: "official",
    summary: "Trang cơ quan được lưu làm metadata nguồn trong UI Preview.",
    verified: false,
    verificationNote:
      "Cần biên tập viên kiểm tra lại phạm vi nội dung trước khi công bố.",
    indexStatus: "not_indexed",
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
  },
];

const illustrativeCoordinates = (latitude: number, longitude: number) => ({
  latitude,
  longitude,
  verified: false,
  verificationNote:
    "Tọa độ minh họa cho UI Preview; cần đối chiếu dữ liệu địa lý trước khi công bố.",
});

export const previewHeritages: PreviewHeritage[] = [
  {
    id: "preview-heritage-thap-rua",
    name: "Tháp Rùa",
    slug: "thap-rua",
    province: "Hà Nội",
    address: "Hồ Hoàn Kiếm, Hà Nội",
    category: "monument",
    period: "Cuối thế kỷ XIX",
    introduction:
      "Hồ sơ minh họa về một công trình nằm trong không gian Hồ Hoàn Kiếm.",
    history:
      "Thông tin lịch sử trong bản Preview chỉ phục vụ kiểm thử bố cục và cần được đối chiếu nguồn trước khi sử dụng.",
    culturalValue:
      "Bản ghi minh họa cách trình bày mối liên hệ giữa công trình và cảnh quan đô thị.",
    tags: ["Hồ Gươm", "Kiến trúc", "Hà Nội"],
    coordinates: illustrativeCoordinates(21.02877, 105.85247),
    media: [
      {
        id: "preview-media-thap-rua",
        kind: "image",
        url: "/demo-thap-rua.jpg",
        alt: "Ảnh minh họa Tháp Rùa trong UI Preview",
        caption:
          "Ảnh mẫu đi kèm frontend; quyền tái sử dụng cần được xác nhận.",
        verified: false,
      },
    ],
    sourceIds: ["preview-source-thap-rua-reference"],
    publicationStatus: "published",
    illustrative: true,
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
  },
  {
    id: "preview-heritage-van-mieu",
    name: "Văn Miếu – Quốc Tử Giám",
    slug: "van-mieu-quoc-tu-giam",
    province: "Hà Nội",
    address: "Quận Đống Đa, Hà Nội",
    category: "temple",
    period: "Thời Lý và các giai đoạn kế tiếp",
    introduction:
      "Hồ sơ mô phỏng một quần thể gắn với lịch sử giáo dục và khoa cử.",
    history: "Nội dung đang chờ biên tập và kiểm chứng nguồn.",
    culturalValue:
      "Dữ liệu mẫu minh họa các trường thông tin văn hóa, kiến trúc và giáo dục.",
    tags: ["Giáo dục", "Khoa cử", "Kiến trúc"],
    coordinates: illustrativeCoordinates(21.02773, 105.83546),
    media: [
      {
        id: "preview-media-van-mieu",
        kind: "image",
        url: "/heritages/van-mieu.jpg",
        alt: "Khuê Văn Các trong quần thể Văn Miếu – Quốc Tử Giám",
        caption:
          "Ảnh mẫu Khuê Văn Các đi kèm repository; metadata bản quyền đang được bổ sung.",
        verified: false,
      },
    ],
    sourceIds: [],
    publicationStatus: "published",
    illustrative: true,
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
  },
  {
    id: "preview-heritage-hoang-thanh",
    name: "Hoàng thành Thăng Long",
    slug: "hoang-thanh-thang-long",
    province: "Hà Nội",
    address: "Quận Ba Đình, Hà Nội",
    category: "archaeology",
    period: "Nhiều thời kỳ lịch sử",
    introduction:
      "Hồ sơ mô phỏng một không gian khảo cổ và trung tâm quyền lực qua nhiều giai đoạn.",
    history: "Cần đọc nguồn chính thức để hoàn thiện niên biểu chi tiết.",
    culturalValue:
      "Fixture minh họa cách liên kết hồ sơ di sản với nguồn danh mục chính thức.",
    tags: ["Khảo cổ", "Kinh đô", "Di sản thế giới"],
    coordinates: illustrativeCoordinates(21.03522, 105.84025),
    media: [
      {
        id: "preview-media-hoang-thanh",
        kind: "image",
        url: "/heritages/hoang-thanh.jpg",
        alt: "Cổng Đoan Môn của Hoàng thành Thăng Long",
        caption: "Minhle817 / Wikimedia Commons · CC BY-SA 4.0. Ảnh năm 2021.",
        verified: false,
      },
    ],
    sourceIds: ["preview-source-hoang-thanh-unesco"],
    publicationStatus: "published",
    illustrative: true,
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
  },
  {
    id: "preview-heritage-chua-mot-cot",
    name: "Chùa Một Cột",
    slug: "chua-mot-cot",
    province: "Hà Nội",
    address: "Quận Ba Đình, Hà Nội",
    category: "temple",
    period: "Khởi dựng thời Lý",
    introduction:
      "Hồ sơ minh họa một công trình có hình thức kiến trúc gắn với biểu tượng hoa sen.",
    history: "Dữ liệu đang chờ đối chiếu nguồn và lịch sử tu bổ.",
    culturalValue:
      "Nội dung Preview dùng để thử các trường văn hóa và kiến trúc, không phải bản thuyết minh đã duyệt.",
    tags: ["Phật giáo", "Hoa sen", "Kiến trúc"],
    coordinates: illustrativeCoordinates(21.03586, 105.83364),
    media: [
      {
        id: "preview-media-chua-mot-cot",
        kind: "image",
        url: "/heritages/chua-mot-cot.jpg",
        alt: "Chùa Một Cột bên hồ sen tại Hà Nội",
        caption:
          "Ảnh mẫu Chùa Một Cột đi kèm repository; metadata bản quyền đang được bổ sung.",
        verified: false,
      },
    ],
    sourceIds: [],
    publicationStatus: "published",
    illustrative: true,
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
  },
  {
    id: "preview-heritage-co-do-hue",
    name: "Quần thể di tích Cố đô Huế",
    slug: "quan-the-di-tich-co-do-hue",
    province: "Thành phố Huế",
    address: "Thành phố Huế, Việt Nam",
    category: "monument",
    period: "Triều Nguyễn",
    introduction:
      "Hồ sơ mô phỏng một quần thể cung điện, thành quách và cảnh quan văn hóa.",
    history: "Thông tin chi tiết cần được biên tập từ nguồn chuyên môn.",
    culturalValue:
      "Fixture hỗ trợ kiểm thử nội dung dài và liên kết nguồn danh mục UNESCO.",
    tags: ["Cung đình", "Kiến trúc", "Di sản thế giới"],
    coordinates: illustrativeCoordinates(16.46979, 107.57747),
    media: [
      {
        id: "preview-media-co-do-hue",
        kind: "image",
        url: "/heritages/co-do-hue.jpg",
        alt: "Ngọ Môn, lối vào Hoàng thành Huế",
        caption:
          "Dennis G. Jarvis / Wikimedia Commons · CC BY-SA 2.0. Ảnh năm 2009, bản thu nhỏ.",
        verified: false,
      },
    ],
    sourceIds: ["preview-source-hue-unesco"],
    publicationStatus: "published",
    illustrative: true,
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
  },
  {
    id: "preview-heritage-hoi-an",
    name: "Đô thị cổ Hội An",
    slug: "do-thi-co-hoi-an",
    province: "Quảng Nam",
    address: "Thành phố Hội An, Quảng Nam",
    category: "monument",
    period: "Thương cảng lịch sử",
    introduction:
      "Hồ sơ mô phỏng một đô thị lịch sử gắn với giao lưu văn hóa và thương mại.",
    history: "Niên biểu và diễn giải đang chờ biên tập.",
    culturalValue:
      "Dữ liệu minh họa các chủ đề về cảnh quan đô thị, kiến trúc và giao thương.",
    tags: ["Phố cổ", "Giao thương", "Di sản thế giới"],
    coordinates: illustrativeCoordinates(15.87705, 108.32676),
    media: [
      {
        id: "preview-media-hoi-an",
        kind: "image",
        url: "/heritages/hoi-an.jpg",
        alt: "Kiến trúc và cảnh quan trong Đô thị cổ Hội An",
        caption:
          "Andre Hospers / Wikimedia Commons · CC BY 4.0. Ảnh năm 2025, bản thu nhỏ.",
        verified: false,
      },
    ],
    sourceIds: ["preview-source-hoi-an-unesco"],
    publicationStatus: "published",
    illustrative: true,
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
  },
  {
    id: "preview-heritage-my-son",
    name: "Thánh địa Mỹ Sơn",
    slug: "thanh-dia-my-son",
    province: "Quảng Nam",
    address: "Huyện Duy Xuyên, Quảng Nam",
    category: "archaeology",
    period: "Văn hóa Chăm",
    introduction:
      "Hồ sơ mô phỏng một quần thể đền tháp trong cảnh quan thung lũng.",
    history: "Dữ liệu chi tiết cần được đối chiếu tài liệu chuyên môn.",
    culturalValue:
      "Fixture minh họa các trường nghệ thuật, kỹ thuật xây dựng và khảo cổ.",
    tags: ["Chăm", "Đền tháp", "Khảo cổ"],
    coordinates: illustrativeCoordinates(15.76416, 108.12444),
    media: [
      {
        id: "preview-media-my-son",
        kind: "image",
        url: "/heritages/my-son.jpg",
        alt: "Một đền tháp gạch tại Thánh địa Mỹ Sơn",
        caption:
          "JL Cogburn / Wikimedia Commons · CC BY-SA 2.0. Ảnh năm 2017, bản thu nhỏ.",
        verified: false,
      },
    ],
    sourceIds: ["preview-source-my-son-unesco"],
    publicationStatus: "published",
    illustrative: true,
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
  },
  {
    id: "preview-heritage-bao-tang-lich-su",
    name: "Bảo tàng Lịch sử Quốc gia",
    slug: "bao-tang-lich-su-quoc-gia",
    province: "Hà Nội",
    address: "Hà Nội",
    category: "museum",
    period: "Hồ sơ đang hoàn thiện",
    introduction:
      "Bản ghi nháp dùng để kiểm thử trạng thái thiếu tọa độ và quy trình biên tập của quản trị viên.",
    history: "Chưa có nội dung đã duyệt.",
    culturalValue: "Chưa có nội dung đã duyệt.",
    tags: ["Bảo tàng", "Hiện vật", "Lịch sử"],
    coordinates: null,
    media: [],
    sourceIds: ["preview-source-museum-official"],
    publicationStatus: "draft",
    illustrative: true,
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
  },
];

export const previewFeedback: PreviewFeedback[] = [
  {
    id: "preview-feedback-001",
    runId: "preview-run-thap-rua-001",
    userId: PREVIEW_ROLE_USER_IDS.user,
    displayName: "Nguyễn Minh Anh",
    rating: "helpful",
    note: "Bố cục câu trả lời dễ theo dõi; đây là phản hồi mô phỏng.",
    status: "new",
    createdAt: "2026-11-15T01:00:00.000Z",
    updatedAt: "2026-11-15T01:00:00.000Z",
  },
  {
    id: "preview-feedback-002",
    runId: "preview-run-hoang-thanh-001",
    userId: PREVIEW_ROLE_USER_IDS.guest,
    displayName: "Khách tham quan",
    rating: "needs_review",
    note: "Cần làm rõ nhãn nguồn đã kiểm chứng và nguồn minh họa.",
    status: "reviewed",
    createdAt: "2026-11-15T02:00:00.000Z",
    updatedAt: "2026-11-15T03:00:00.000Z",
  },
];

const initialFavorites: Record<string, string[]> = {
  [PREVIEW_GUEST_IDENTITY]: [],
  [PREVIEW_ROLE_USER_IDS.guest]: ["preview-heritage-thap-rua"],
  [PREVIEW_ROLE_USER_IDS.user]: [
    "preview-heritage-thap-rua",
    "preview-heritage-hoang-thanh",
  ],
  [PREVIEW_ROLE_USER_IDS.admin]: ["preview-heritage-co-do-hue"],
};

export function createPreviewInitialState(): PreviewState {
  return structuredClone({
    users: previewUsers,
    heritages: previewHeritages,
    contentSources: previewContentSources,
    feedback: previewFeedback,
    favoriteHeritageIdsByIdentity: initialFavorites,
    currentUserId: null,
  });
}
