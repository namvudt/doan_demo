import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Database,
  Edit3,
  FileWarning,
  Landmark,
  MessageSquareWarning,
  Plus,
  Search,
  Trash2,
  UsersRound,
  X,
} from "lucide-react";
import { usePreview } from "../preview/PreviewProvider";
import type {
  PreviewContentSource,
  PreviewContentSourceInput,
  PreviewHeritage,
  PreviewHeritageCategory,
  PreviewHeritageInput,
  PreviewRole,
  PreviewUserStatus,
} from "../preview/types";
import { PreviewValidationError } from "../preview/types";
import { Badge, Button, EmptyState, Field } from "../ui/Ui";

const previewRuns = [
  {
    id: "run-preview-001",
    question: "Những chi tiết kiến trúc nào xuất hiện trong ảnh?",
    status: "succeeded",
    result: "reviewed",
    stages: 7,
    calls: 5,
    error: "",
  },
  {
    id: "run-preview-002",
    question: "Địa điểm này có thể thuộc giai đoạn nào?",
    status: "succeeded",
    result: "insufficient_evidence",
    stages: 6,
    calls: 4,
    error: "",
  },
  {
    id: "run-preview-003",
    question: "Hãy xác định chính xác di tích trong ảnh.",
    status: "failed",
    result: "failed",
    stages: 3,
    calls: 2,
    error: "ProviderUnavailable (mô phỏng)",
  },
];

export function AdminDashboardPage() {
  const preview = usePreview();
  const published = preview.heritages.filter(
    (item) => item.publicationStatus === "published",
  ).length;
  const located = preview.heritages.filter((item) => item.coordinates).length;
  const activeUsers = preview.users.filter(
    (item) => item.status === "active",
  ).length;
  const pendingFeedback = preview.feedback.filter(
    (item) => item.status === "new",
  ).length;
  const cards = [
    {
      label: "Hồ sơ đã công bố",
      value: published,
      detail: `${preview.heritages.length - published} bản nháp`,
      icon: <Landmark size={20} />,
      to: "/admin/heritages",
    },
    {
      label: "Có dữ liệu vị trí",
      value: located,
      detail: `${preview.heritages.length - located} thiếu tọa độ`,
      icon: <Activity size={20} />,
      to: "/map",
    },
    {
      label: "Người dùng hoạt động",
      value: activeUsers,
      detail: `${preview.users.length} danh tính mô phỏng`,
      icon: <UsersRound size={20} />,
      to: "/admin/users",
    },
    {
      label: "Phản hồi mới",
      value: pendingFeedback,
      detail: `${preview.feedback.length} phản hồi tổng cộng`,
      icon: <MessageSquareWarning size={20} />,
      to: "/admin/feedback",
    },
  ];
  return (
    <div className="admin-content">
      <div className="metric-grid">
        {cards.map((card) => (
          <Link to={card.to} className="metric-card" key={card.label}>
            <span className="metric-icon">{card.icon}</span>
            <span className="metric-value">{card.value}</span>
            <strong>{card.label}</strong>
            <small>{card.detail}</small>
          </Link>
        ))}
      </div>
      <div className="admin-two-columns">
        <section className="panel">
          <div className="section-head">
            <div>
              <span className="eyebrow">CHẤT LƯỢNG DỮ LIỆU</span>
              <h2>Việc cần chú ý</h2>
            </div>
          </div>
          <ul className="quality-list">
            <li>
              <AlertTriangle size={17} />
              <span>
                <strong>
                  {preview.heritages.filter((item) => !item.coordinates).length}{" "}
                  hồ sơ chưa có tọa độ
                </strong>
                <small>Không xuất hiện dưới dạng marker.</small>
              </span>
            </li>
            <li>
              <FileWarning size={17} />
              <span>
                <strong>
                  {
                    preview.contentSources.filter((item) => !item.verified)
                      .length
                  }{" "}
                  nguồn chưa xác minh metadata
                </strong>
                <small>Không đồng nghĩa nguồn đã được đưa vào RAG.</small>
              </span>
            </li>
            <li>
              <CheckCircle2 size={17} />
              <span>
                <strong>Dữ liệu dùng chung đã kết nối</strong>
                <small>
                  Thay đổi catalog hiển thị ngay ở thư viện và bản đồ.
                </small>
              </span>
            </li>
          </ul>
        </section>
        <section className="panel">
          <div className="section-head">
            <div>
              <span className="eyebrow">RUN PREVIEW</span>
              <h2>Trạng thái mô phỏng</h2>
            </div>
            <Link to="/admin/runs">Xem tất cả</Link>
          </div>
          <div className="compact-run-list">
            {previewRuns.map((run) => (
              <div key={run.id}>
                <span className={`status-dot ${run.status}`} />
                <span>
                  <strong>{run.question}</strong>
                  <small>{run.id}</small>
                </span>
                <Badge tone={run.status === "failed" ? "red" : "green"}>
                  {run.result}
                </Badge>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

const blankHeritage: PreviewHeritageInput = {
  name: "",
  province: "",
  address: "",
  category: "monument",
  period: "",
  introduction: "",
  history: "",
  culturalValue: "",
  tags: [],
  coordinates: null,
  media: [],
  sourceIds: [],
  publicationStatus: "draft",
};

function HeritageEditor({
  item,
  onClose,
}: {
  item?: PreviewHeritage;
  onClose: () => void;
}) {
  const preview = usePreview();
  const [values, setValues] = useState<PreviewHeritageInput>(() =>
    item
      ? {
          ...item,
          tags: [...item.tags],
          media: [...item.media],
          sourceIds: [...item.sourceIds],
        }
      : blankHeritage,
  );
  const [lat, setLat] = useState(item?.coordinates?.latitude.toString() || "");
  const [lng, setLng] = useState(item?.coordinates?.longitude.toString() || "");
  const [imageUrl, setImageUrl] = useState(item?.media[0]?.url || "");
  const [imageAlt, setImageAlt] = useState(item?.media[0]?.alt || "");
  const [imageCaption, setImageCaption] = useState(
    item?.media[0]?.caption || "",
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (dirty) event.preventDefault();
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty]);
  const update = <K extends keyof PreviewHeritageInput>(
    key: K,
    value: PreviewHeritageInput[K],
  ) => {
    setValues((current) => ({ ...current, [key]: value }));
    setDirty(true);
  };
  const close = () => {
    if (!dirty || window.confirm("Bỏ các thay đổi chưa lưu?")) onClose();
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setErrors({});
    try {
      const latitudeText = lat.trim();
      const longitudeText = lng.trim();
      if (Boolean(latitudeText) !== Boolean(longitudeText)) {
        setErrors({
          coordinates: "Hãy nhập đủ cả vĩ độ và kinh độ, hoặc để trống cả hai.",
        });
        return;
      }
      const coordinates =
        latitudeText && longitudeText
          ? {
              latitude: Number(latitudeText),
              longitude: Number(longitudeText),
              verified: false,
              verificationNote:
                "Tọa độ nhập trong UI Preview, chưa được backend xác minh.",
            }
          : null;
      const media = imageUrl.trim()
        ? [
            {
              id: item?.media[0]?.id || "",
              kind: "image" as const,
              url: imageUrl.trim(),
              alt: imageAlt.trim(),
              caption: imageCaption.trim(),
              verified: false,
            },
          ]
        : [];
      const input = { ...values, coordinates, media };
      if (item) preview.updateHeritage(item.id, input);
      else preview.createHeritage(input);
      setDirty(false);
      onClose();
    } catch (reason) {
      if (reason instanceof PreviewValidationError) setErrors(reason.fields);
      else
        setErrors({
          form:
            reason instanceof Error ? reason.message : "Không thể lưu hồ sơ.",
        });
    }
  };
  return (
    <div className="dialog-backdrop" onMouseDown={close}>
      <section
        className="dialog-card editor-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="heritage-editor-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="dialog-head">
          <div>
            <span className="eyebrow">{item ? "CHỈNH SỬA" : "TẠO MỚI"}</span>
            <h2 id="heritage-editor-title">
              {item ? item.name : "Hồ sơ di sản minh họa"}
            </h2>
          </div>
          <button className="icon-button" aria-label="Đóng" onClick={close}>
            <X size={19} />
          </button>
        </div>
        <form className="editor-form" onSubmit={submit}>
          <div className="form-grid-2">
            <Field label="Tên di sản" error={errors.name}>
              <input
                value={values.name}
                onChange={(e) => update("name", e.target.value)}
                aria-invalid={Boolean(errors.name)}
              />
            </Field>
            <Field label="Tỉnh/thành" error={errors.province}>
              <input
                value={values.province}
                onChange={(e) => update("province", e.target.value)}
              />
            </Field>
          </div>
          <Field label="Địa chỉ" error={errors.address}>
            <input
              value={values.address}
              onChange={(e) => update("address", e.target.value)}
            />
          </Field>
          <div className="form-grid-3">
            <Field label="Loại hình">
              <select
                value={values.category}
                onChange={(e) =>
                  update("category", e.target.value as PreviewHeritageCategory)
                }
              >
                <option value="monument">Di tích lịch sử</option>
                <option value="temple">Tín ngưỡng · tôn giáo</option>
                <option value="museum">Bảo tàng</option>
                <option value="archaeology">Khảo cổ</option>
              </select>
            </Field>
            <Field label="Giai đoạn">
              <input
                value={values.period}
                onChange={(e) => update("period", e.target.value)}
              />
            </Field>
            <Field label="Xuất bản">
              <select
                value={values.publicationStatus}
                onChange={(e) =>
                  update(
                    "publicationStatus",
                    e.target.value as "draft" | "published",
                  )
                }
              >
                <option value="draft">Bản nháp</option>
                <option value="published">Công bố</option>
              </select>
            </Field>
          </div>
          <Field label="Giới thiệu" error={errors.introduction}>
            <textarea
              rows={3}
              value={values.introduction}
              onChange={(e) => update("introduction", e.target.value)}
            />
          </Field>
          <div className="form-grid-2">
            <Field label="Lịch sử">
              <textarea
                rows={5}
                value={values.history}
                onChange={(e) => update("history", e.target.value)}
              />
            </Field>
            <Field label="Giá trị văn hóa">
              <textarea
                rows={5}
                value={values.culturalValue}
                onChange={(e) => update("culturalValue", e.target.value)}
              />
            </Field>
          </div>
          <div className="form-grid-2">
            <Field label="Vĩ độ" hint="-90 đến 90" error={errors.coordinates}>
              <input
                inputMode="decimal"
                value={lat}
                onChange={(e) => {
                  setLat(e.target.value);
                  setDirty(true);
                }}
              />
            </Field>
            <Field
              label="Kinh độ"
              hint="-180 đến 180"
              error={errors.coordinates}
            >
              <input
                inputMode="decimal"
                value={lng}
                onChange={(e) => {
                  setLng(e.target.value);
                  setDirty(true);
                }}
              />
            </Field>
          </div>
          <div className="form-grid-3">
            <Field
              label="Ảnh minh họa"
              hint="Đường dẫn root-relative, ví dụ /demo-thap-rua.jpg"
            >
              <input
                value={imageUrl}
                onChange={(e) => {
                  setImageUrl(e.target.value);
                  setDirty(true);
                }}
              />
            </Field>
            <Field label="Văn bản thay thế">
              <input
                value={imageAlt}
                onChange={(e) => {
                  setImageAlt(e.target.value);
                  setDirty(true);
                }}
              />
            </Field>
            <Field label="Chú thích ảnh">
              <input
                value={imageCaption}
                onChange={(e) => {
                  setImageCaption(e.target.value);
                  setDirty(true);
                }}
              />
            </Field>
          </div>
          {item && (
            <Field
              label="Nguồn metadata liên kết"
              hint="Có thể chọn nhiều; quản lý nội dung nguồn ở mô-đun Nguồn."
            >
              <select
                multiple
                value={values.sourceIds || []}
                onChange={(e) =>
                  update(
                    "sourceIds",
                    Array.from(
                      e.target.selectedOptions,
                      (option) => option.value,
                    ),
                  )
                }
              >
                {preview.contentSources
                  .filter((source) => source.heritageId === item.id)
                  .map((source) => (
                    <option value={source.id} key={source.id}>
                      {source.title}
                    </option>
                  ))}
              </select>
            </Field>
          )}
          <Field label="Thẻ" hint="Phân cách bằng dấu phẩy">
            <input
              value={(values.tags || []).join(", ")}
              onChange={(e) =>
                update(
                  "tags",
                  e.target.value
                    .split(",")
                    .map((value) => value.trim())
                    .filter(Boolean),
                )
              }
            />
          </Field>
          {errors.form && (
            <p className="form-alert" role="alert">
              {errors.form}
            </p>
          )}
          <div className="dialog-actions">
            <Button type="button" tone="secondary" onClick={close}>
              Hủy
            </Button>
            <Button type="submit">{item ? "Lưu thay đổi" : "Tạo hồ sơ"}</Button>
          </div>
        </form>
      </section>
    </div>
  );
}

export function AdminHeritagesPage() {
  const preview = usePreview();
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<PreviewHeritage | "new" | null>(null);
  const items = preview.heritages.filter((item) =>
    `${item.name} ${item.province}`
      .toLocaleLowerCase("vi")
      .includes(query.toLocaleLowerCase("vi")),
  );
  return (
    <div className="admin-content">
      <div className="admin-toolbar">
        <label className="search-field">
          <Search size={17} />
          <span className="sr-only">Tìm hồ sơ</span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Tìm tên hoặc địa phương…"
          />
        </label>
        <Button onClick={() => setEditing("new")}>
          <Plus size={16} /> Thêm di sản
        </Button>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Hồ sơ</th>
              <th>Loại hình</th>
              <th>Vị trí</th>
              <th>Trạng thái</th>
              <th>
                <span className="sr-only">Thao tác</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>
                  <strong>{item.name}</strong>
                  <small>{item.province}</small>
                </td>
                <td>{item.category}</td>
                <td>
                  {item.coordinates ? (
                    <Badge tone={item.coordinates.verified ? "green" : "gold"}>
                      {item.coordinates.verified ? "Đã xác minh" : "Minh họa"}
                    </Badge>
                  ) : (
                    <Badge>Thiếu tọa độ</Badge>
                  )}
                </td>
                <td>
                  <Badge
                    tone={
                      item.publicationStatus === "published"
                        ? "green"
                        : "neutral"
                    }
                  >
                    {item.publicationStatus === "published"
                      ? "Đã công bố"
                      : "Bản nháp"}
                  </Badge>
                </td>
                <td>
                  <div className="row-actions">
                    <button
                      aria-label={`Sửa ${item.name}`}
                      onClick={() => setEditing(item)}
                    >
                      <Edit3 size={16} />
                    </button>
                    <button
                      aria-label={`Xóa ${item.name}`}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Xóa hồ sơ “${item.name}”? Thay đổi sẽ phản ánh trên thư viện, yêu thích và bản đồ.`,
                          )
                        )
                          preview.deleteHeritage(item.id);
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && (
        <HeritageEditor
          item={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}

export function AdminUsersPage() {
  const preview = usePreview();
  const [error, setError] = useState("");
  const mutate = (operation: () => void) => {
    setError("");
    try {
      operation();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Không thể cập nhật người dùng.",
      );
    }
  };
  return (
    <div className="admin-content">
      <div className="section-head">
        <div>
          <h2>Người dùng mô phỏng</h2>
          <p>
            Vai trò và trạng thái này chỉ điều khiển UI Preview, không phải RBAC
            backend.
          </p>
        </div>
        <Badge tone="gold">Preview only</Badge>
      </div>
      {error && (
        <p className="form-alert" role="alert">
          {error}
        </p>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Người dùng</th>
              <th>Vai trò</th>
              <th>Trạng thái</th>
              <th>Tạo lúc</th>
            </tr>
          </thead>
          <tbody>
            {preview.users.map((user) => (
              <tr key={user.id}>
                <td>
                  <strong>{user.fullName}</strong>
                  <small>{user.email}</small>
                </td>
                <td>
                  <select
                    aria-label={`Vai trò ${user.fullName}`}
                    value={user.role}
                    onChange={(e) =>
                      mutate(() =>
                        preview.updateUserRole(
                          user.id,
                          e.target.value as PreviewRole,
                        ),
                      )
                    }
                  >
                    <option value="guest">Khách</option>
                    <option value="user">Người dùng</option>
                    <option value="admin">Quản trị</option>
                  </select>
                </td>
                <td>
                  <select
                    aria-label={`Trạng thái ${user.fullName}`}
                    value={user.status}
                    onChange={(e) =>
                      mutate(() =>
                        preview.updateUserStatus(
                          user.id,
                          e.target.value as PreviewUserStatus,
                        ),
                      )
                    }
                  >
                    <option value="active">Hoạt động</option>
                    <option value="suspended">Tạm khóa</option>
                  </select>
                </td>
                <td>{new Date(user.createdAt).toLocaleDateString("vi-VN")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const blankSource: PreviewContentSourceInput = {
  heritageId: "",
  title: "",
  publisher: "",
  url: "https://",
  kind: "reference",
  summary: "",
  verified: false,
  verificationNote: "Chưa xác minh metadata trong UI Preview.",
};
export function AdminSourcesPage() {
  const preview = usePreview();
  const [editing, setEditing] = useState<PreviewContentSource | null>(null);
  const [creating, setCreating] = useState(false);
  const [values, setValues] = useState<PreviewContentSourceInput>(blankSource);
  const [error, setError] = useState("");
  const open = (source?: PreviewContentSource) => {
    setError("");
    setEditing(source || null);
    setCreating(true);
    setValues(
      source
        ? { ...source }
        : { ...blankSource, heritageId: preview.heritages[0]?.id || "" },
    );
  };
  const save = (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      if (editing) preview.updateContentSource(editing.id, values);
      else preview.createContentSource(values);
      setCreating(false);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Không thể lưu nguồn.",
      );
    }
  };
  return (
    <div className="admin-content">
      <div className="section-head">
        <div>
          <h2>Metadata nguồn nội dung</h2>
          <p>
            Đây là bản ghi nguồn minh họa, không phải chứng cứ truy xuất hoặc
            trạng thái corpus RAG.
          </p>
        </div>
        <Button onClick={() => open()}>
          <Plus size={16} /> Thêm nguồn
        </Button>
      </div>
      <div className="source-admin-grid">
        {preview.contentSources.map((source) => (
          <article className="panel" key={source.id}>
            <div className="source-card-head">
              <Database size={18} />
              <Badge tone={source.verified ? "green" : "gold"}>
                {source.verified ? "Metadata đã xác minh" : "Chưa xác minh"}
              </Badge>
            </div>
            <h3>{source.title}</h3>
            <p>{source.publisher}</p>
            <small>
              Index: chưa lập chỉ mục · không có thao tác ingest/reindex
            </small>
            <div className="card-actions">
              <button onClick={() => open(source)}>Chỉnh sửa</button>
              <button
                onClick={() => {
                  if (window.confirm("Xóa nguồn metadata này?"))
                    preview.deleteContentSource(source.id);
                }}
              >
                Xóa
              </button>
            </div>
          </article>
        ))}
      </div>
      {creating && (
        <div className="dialog-backdrop">
          <section
            className="dialog-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="source-title"
          >
            <div className="dialog-head">
              <h2 id="source-title">{editing ? "Sửa nguồn" : "Thêm nguồn"}</h2>
              <button
                className="icon-button"
                aria-label="Đóng"
                onClick={() => setCreating(false)}
              >
                <X size={19} />
              </button>
            </div>
            <form className="form-stack" onSubmit={save}>
              <Field label="Hồ sơ di sản">
                <select
                  value={values.heritageId}
                  onChange={(e) =>
                    setValues({ ...values, heritageId: e.target.value })
                  }
                >
                  {preview.heritages.map((item) => (
                    <option value={item.id} key={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Tiêu đề">
                <input
                  value={values.title}
                  onChange={(e) =>
                    setValues({ ...values, title: e.target.value })
                  }
                />
              </Field>
              <Field label="Nhà xuất bản">
                <input
                  value={values.publisher}
                  onChange={(e) =>
                    setValues({ ...values, publisher: e.target.value })
                  }
                />
              </Field>
              <Field label="URL">
                <input
                  type="url"
                  value={values.url}
                  onChange={(e) =>
                    setValues({ ...values, url: e.target.value })
                  }
                />
              </Field>
              <Field label="Tóm tắt">
                <textarea
                  value={values.summary}
                  onChange={(e) =>
                    setValues({ ...values, summary: e.target.value })
                  }
                />
              </Field>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={values.verified}
                  onChange={(e) =>
                    setValues({ ...values, verified: e.target.checked })
                  }
                />{" "}
                Metadata đã được kiểm tra thủ công
              </label>
              {error && (
                <p className="form-alert" role="alert">
                  {error}
                </p>
              )}
              <div className="dialog-actions">
                <Button
                  type="button"
                  tone="secondary"
                  onClick={() => setCreating(false)}
                >
                  Hủy
                </Button>
                <Button type="submit">Lưu metadata</Button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}

export function AdminRunsPage() {
  const [status, setStatus] = useState("");
  const items = previewRuns.filter((run) => !status || run.status === status);
  const [selected, setSelected] = useState(items[0]);
  return (
    <div className="admin-content">
      <div className="admin-toolbar">
        <div>
          <h2>Run mô phỏng</h2>
          <p>Không phải giám sát toàn cục từ backend.</p>
        </div>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Mọi trạng thái</option>
          <option value="succeeded">Succeeded</option>
          <option value="failed">Failed</option>
        </select>
      </div>
      <div className="run-monitor">
        <div className="run-monitor-list">
          {items.map((run) => (
            <button
              key={run.id}
              className={selected?.id === run.id ? "selected" : ""}
              onClick={() => setSelected(run)}
            >
              <span className={`status-dot ${run.status}`} />
              <span>
                <strong>{run.question}</strong>
                <small>{run.id}</small>
              </span>
            </button>
          ))}
        </div>
        {selected ? (
          <article className="panel run-monitor-detail">
            <div className="detail-badges">
              <Badge tone={selected.status === "failed" ? "red" : "green"}>
                {selected.status}
              </Badge>
              <Badge>{selected.result}</Badge>
            </div>
            <h2>{selected.question}</h2>
            <dl className="detail-facts">
              <div>
                <dt>Workflow stages</dt>
                <dd>{selected.stages} snapshots</dd>
              </div>
              <div>
                <dt>Model attempts</dt>
                <dd>{selected.calls} attempts</dd>
              </div>
              <div>
                <dt>Tool/API calls</dt>
                <dd>Không được API hiện tại cung cấp</dd>
              </div>
            </dl>
            {selected.error && <p className="form-alert">{selected.error}</p>}
            <details>
              <summary>Chẩn đoán kỹ thuật mô phỏng</summary>
              <pre>{JSON.stringify(selected, null, 2)}</pre>
            </details>
          </article>
        ) : (
          <EmptyState title="Không có run" icon={<Activity size={27} />}>
            Đổi bộ lọc để xem dữ liệu.
          </EmptyState>
        )}
      </div>
    </div>
  );
}

export function AdminFeedbackPage() {
  const preview = usePreview();
  const [filter, setFilter] = useState("");
  const items = preview.feedback.filter(
    (item) => !filter || item.rating === filter,
  );
  return (
    <div className="admin-content">
      <div className="admin-toolbar">
        <div>
          <h2>Phản hồi mô phỏng</h2>
          <p>
            Backend thật chỉ cho phép đọc/ghi feedback của từng run sở hữu;
            không có danh sách moderation.
          </p>
        </div>
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">Mọi đánh giá</option>
          <option value="helpful">Hữu ích</option>
          <option value="needs_review">Cần xem lại</option>
          <option value="unrated">Chưa đánh giá</option>
        </select>
      </div>
      {items.length ? (
        <div className="feedback-list">
          {items.map((item) => (
            <article className="panel" key={item.id}>
              <div className="feedback-meta">
                <Badge
                  tone={
                    item.rating === "helpful"
                      ? "green"
                      : item.rating === "needs_review"
                        ? "red"
                        : "neutral"
                  }
                >
                  {item.rating}
                </Badge>
                <span>{item.displayName}</span>
                <span>{new Date(item.createdAt).toLocaleString("vi-VN")}</span>
              </div>
              <p>{item.note || "Không có ghi chú."}</p>
              <small>Run: {item.runId}</small>
              <div className="card-actions">
                <button
                  onClick={() =>
                    preview.updateFeedbackStatus(
                      item.id,
                      item.status === "new" ? "reviewed" : "new",
                    )
                  }
                >
                  {item.status === "new" ? "Đánh dấu đã xem" : "Mở lại"}
                </button>
                <button onClick={() => preview.deleteFeedback(item.id)}>
                  Xóa mô phỏng
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState
          title="Không có phản hồi phù hợp"
          icon={<MessageSquareWarning size={27} />}
        >
          Thử thay đổi bộ lọc.
        </EmptyState>
      )}
    </div>
  );
}
