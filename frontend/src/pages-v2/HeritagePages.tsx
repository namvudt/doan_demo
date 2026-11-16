import { useMemo, useState } from "react";
import {
  Link,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  ArrowRight,
  Heart,
  ImageOff,
  Landmark,
  MapPin,
  MessageSquareText,
  Search,
  ShieldAlert,
} from "lucide-react";
import { useApp } from "../app/AppContext";
import { usePreview } from "../preview/PreviewProvider";
import { Badge, Button, EmptyState, StatusCard } from "../ui/Ui";
import { ResilientImage } from "../ui/ResilientImage";
import {
  coordinateLabel,
  toHeritageDisplay,
  useHeritageCatalog,
  useHeritageRecord,
  type HeritageDisplay,
} from "../ui/useHeritageCatalog";

const categoryLabels: Record<string, string> = {
  monument: "Di tích lịch sử",
  temple: "Tín ngưỡng · tôn giáo",
  museum: "Bảo tàng",
  archaeology: "Khảo cổ",
};

function ApiFavoriteButton({
  id,
  text = false,
}: {
  id: string;
  text?: boolean;
}) {
  const app = useApp();
  const navigate = useNavigate();
  const location = useLocation();
  const [busy, setBusy] = useState(false);
  const saved = app.heritageFavorites.some((item) => item.heritage_id === id);
  if (!app.capabilities?.features?.heritage_favorites) return null;
  const toggle = async () => {
    if (!app.account) {
      navigate("/login", {
        state: { from: location.pathname + location.search },
      });
      return;
    }
    setBusy(true);
    try {
      await app.setHeritageFavorite(id, !saved);
    } catch (reason) {
      app.notify(
        reason instanceof Error ? reason.message : "Không lưu được di sản.",
        "error",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <button
      type="button"
      className={text ? "button ghost" : saved ? "favorite active" : "favorite"}
      disabled={busy || app.heritageFavoritesLoading}
      aria-label={saved ? "Bỏ yêu thích di sản" : "Thêm yêu thích di sản"}
      onClick={() => void toggle()}
    >
      <Heart size={17} fill={saved ? "currentColor" : "none"} />
      {text ? (saved ? " Đã yêu thích" : " Yêu thích") : null}
    </button>
  );
}

function HeritageImage({
  item,
  detail = false,
}: {
  item: HeritageDisplay;
  detail?: boolean;
}) {
  const media = item.media[0];
  return (
    <ResilientImage
      src={media?.url}
      alt={media?.alt || `Tư liệu về ${item.name}`}
      label={item.name}
      loading={detail ? "eager" : "lazy"}
      retryable={detail}
    />
  );
}

function HeritageCard({ item }: { item: HeritageDisplay }) {
  const app = useApp();
  const preview = usePreview();
  const navigate = useNavigate();
  const location = useLocation();
  const saved = preview.favoriteHeritageIds.includes(item.id);
  const favorite = () => {
    if (!preview.isAuthenticated) {
      navigate("/login", {
        state: { from: location.pathname + location.search },
      });
      return;
    }
    preview.toggleFavorite(item.id);
  };
  return (
    <article className="heritage-card">
      <Link to={`/heritages/${item.id}`} className="heritage-card-image">
        <HeritageImage item={item} />
        {item.illustrative && <Badge tone="gold">Minh họa</Badge>}
      </Link>
      <div className="heritage-card-body">
        <div className="card-meta">
          <span>{categoryLabels[item.category] || item.category}</span>
          <span>·</span>
          <span>{item.province}</span>
        </div>
        <Link to={`/heritages/${item.id}`}>
          <h2>{item.name}</h2>
        </Link>
        <p>{item.introduction}</p>
        <div className="card-actions">
          <Link to={`/heritages/${item.id}`}>
            Xem hồ sơ <ArrowRight size={14} />
          </Link>
          {app.mode === "preview" && (
            <button
              type="button"
              aria-label={saved ? "Bỏ yêu thích" : "Thêm yêu thích"}
              className={saved ? "favorite active" : "favorite"}
              onClick={favorite}
            >
              <Heart size={17} fill={saved ? "currentColor" : "none"} />
            </button>
          )}
          {app.mode === "api" && <ApiFavoriteButton id={item.id} />}
        </div>
      </div>
    </article>
  );
}

export function HeritagesPage() {
  const app = useApp();
  const preview = usePreview();
  const catalog = useHeritageCatalog();
  const records = useMemo<HeritageDisplay[]>(
    () =>
      app.mode === "api"
        ? catalog.records.map(toHeritageDisplay)
        : preview.heritages,
    [app.mode, catalog.records, preview.heritages],
  );
  const [params, setParams] = useSearchParams();
  const query = params.get("q") || "";
  const province = params.get("province") || "";
  const category = params.get("category") || "";
  const provinces = useMemo(
    () => [...new Set(records.map((item) => item.province))].sort(),
    [records],
  );
  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("vi");
    return records.filter((item) => {
      if (item.publicationStatus !== "published") return false;
      if (province && item.province !== province) return false;
      if (category && item.category !== category) return false;
      return (
        !normalized ||
        `${item.name} ${item.province} ${item.tags.join(" ")}`
          .toLocaleLowerCase("vi")
          .includes(normalized)
      );
    });
  }, [records, query, province, category]);

  const update = (name: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next, { replace: true });
  };

  return (
    <div className="page-shell">
      <header className="page-heading library-heading">
        <div>
          <span className="eyebrow">THƯ VIỆN DI SẢN</span>
          <h1>Những địa điểm, những lớp thời gian</h1>
          <p>
            Tìm hồ sơ {app.mode === "preview" ? "minh họa " : ""}theo địa phương
            và loại hình, rồi mở trong bản đồ hoặc hỏi cùng AI.
          </p>
        </div>
        <Link
          to={{
            pathname: "/map",
            search: params.toString() ? `?${params.toString()}` : "",
          }}
          className="button secondary"
        >
          <MapPin size={16} /> Xem bản đồ
        </Link>
      </header>

      {app.mode === "api" && !catalog.supported ? (
        <section className="api-catalog-state">
          <StatusCard
            kind={
              !app.capabilities && !app.capabilitiesError
                ? "loading"
                : "warning"
            }
            title={
              !app.capabilities && !app.capabilitiesError
                ? "Đang kiểm tra catalog di sản…"
                : "Backend chưa cung cấp catalog di sản"
            }
          >
            {app.capabilitiesError ||
              "Bạn có thể dùng sample ảnh từ backend để bắt đầu hỏi đáp với AI."}
          </StatusCard>
          <div className="section-head">
            <div>
              <span className="eyebrow">SAMPLE ẢNH TỪ API</span>
              <h2>Chọn ảnh để hỏi</h2>
            </div>
            <Button tone="secondary" onClick={app.refreshApiSamples}>
              Tải lại
            </Button>
          </div>
          {app.apiSamplesLoading ? (
            <StatusCard kind="loading" title="Đang tải danh sách sample…" />
          ) : app.apiSamplesError ? (
            <StatusCard kind="error" title="Không tải được sample">
              {app.apiSamplesError}
            </StatusCard>
          ) : app.apiSamples.length ? (
            <div className="sample-grid">
              {app.apiSamples.map((sample) => (
                <article className="sample-card" key={sample.sample_id}>
                  <div className="sample-icon">
                    <Landmark size={22} />
                  </div>
                  <div>
                    <strong>{sample.title}</strong>
                    <small>ID: {sample.sample_id}</small>
                  </div>
                  <Link
                    to={`/chat?sample=${encodeURIComponent(sample.sample_id)}`}
                    className="button secondary compact"
                  >
                    Dùng sample
                  </Link>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState
              title="Backend chưa cung cấp sample"
              icon={<ImageOff size={27} />}
            >
              Bạn vẫn có thể tải ảnh của mình trong trang Hỏi đáp.
            </EmptyState>
          )}
        </section>
      ) : (
        <>
          {app.mode === "api" && (
            <div className="section-head">
              <Badge tone="green">Dữ liệu backend</Badge>
              <Button
                tone="ghost"
                disabled={catalog.loading}
                onClick={catalog.refresh}
              >
                Tải lại dữ liệu
              </Button>
            </div>
          )}
          {catalog.error && (
            <StatusCard kind="error" title="Không tải được catalog di sản">
              {catalog.error}
            </StatusCard>
          )}
          {app.mode === "api" && catalog.hasMore && (
            <StatusCard
              kind="warning"
              title={`Đang hiển thị ${records.length}/${catalog.total} hồ sơ`}
            >
              Bộ lọc áp dụng trên các hồ sơ đã tải.{" "}
              <Button
                tone="secondary"
                disabled={catalog.loading}
                onClick={catalog.loadMore}
              >
                Tải thêm hồ sơ
              </Button>
            </StatusCard>
          )}
          <section className="filter-bar" aria-label="Bộ lọc di sản">
            <label className="search-field">
              <Search size={18} />
              <span className="sr-only">Tìm di sản</span>
              <input
                value={query}
                onChange={(e) => update("q", e.target.value)}
                placeholder="Tìm theo tên, địa phương, từ khóa…"
              />
            </label>
            <label>
              <span className="sr-only">Địa phương</span>
              <select
                value={province}
                onChange={(e) => update("province", e.target.value)}
              >
                <option value="">Tất cả địa phương</option>
                {provinces.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label>
              <span className="sr-only">Loại hình</span>
              <select
                value={category}
                onChange={(e) => update("category", e.target.value)}
              >
                <option value="">Tất cả loại hình</option>
                {Object.entries(categoryLabels).map(([value, label]) => (
                  <option value={value} key={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <span className="result-count">
              {filtered.length} hồ sơ
              {app.mode === "preview" ? " minh họa" : " từ backend"}
            </span>
          </section>
          {catalog.loading && !records.length ? (
            <StatusCard kind="loading" title="Đang tải hồ sơ di sản…" />
          ) : filtered.length ? (
            <section className="heritage-grid">
              {filtered.map((item) => (
                <HeritageCard item={item} key={item.id} />
              ))}
            </section>
          ) : !catalog.error ? (
            <EmptyState
              title="Không có kết quả phù hợp"
              icon={<Search size={27} />}
            >
              Thử bỏ bớt bộ lọc hoặc dùng từ khóa khác.
            </EmptyState>
          ) : null}
        </>
      )}
    </div>
  );
}

export function HeritageDetailPage() {
  const app = useApp();
  const preview = usePreview();
  const { heritageId } = useParams();
  const navigate = useNavigate();
  const catalog = useHeritageRecord(heritageId);
  if (app.mode === "api" && !catalog.supported) {
    return (
      <div className="page-shell narrow-page">
        <StatusCard
          kind={
            !app.capabilities && !app.capabilitiesError ? "loading" : "warning"
          }
          title={
            !app.capabilities && !app.capabilitiesError
              ? "Đang kiểm tra catalog di sản…"
              : "Backend chưa cung cấp catalog di sản"
          }
        >
          {app.capabilitiesError} <Link to="/heritages">Về thư viện</Link>.
        </StatusCard>
      </div>
    );
  }
  if (app.mode === "api" && catalog.loading)
    return (
      <div className="page-shell narrow-page">
        <StatusCard kind="loading" title="Đang tải hồ sơ di sản…" />
      </div>
    );
  if (app.mode === "api" && catalog.error)
    return (
      <div className="page-shell narrow-page">
        <StatusCard kind="error" title="Không tải được hồ sơ di sản">
          {catalog.error}{" "}
          <Button tone="secondary" onClick={catalog.refresh}>
            Thử lại
          </Button>{" "}
          <Link to="/heritages">Về thư viện</Link>
        </StatusCard>
      </div>
    );
  const item: HeritageDisplay | undefined =
    app.mode === "api"
      ? catalog.record && toHeritageDisplay(catalog.record)
      : preview.heritages.find((heritage) => heritage.id === heritageId);
  if (!item)
    return (
      <div className="page-shell">
        <EmptyState title="Không tìm thấy hồ sơ" icon={<Landmark size={28} />}>
          Hồ sơ có thể đã bị xóa hoặc chưa được công bố.{" "}
          <Link to="/heritages">Về thư viện</Link>.
        </EmptyState>
      </div>
    );
  const sources =
    app.mode === "api"
      ? (catalog.record?.information_sources || []).map((source) => ({
          ...source,
          id: source.source_id,
        }))
      : preview.contentSources.filter((source) =>
          item.sourceIds.includes(source.id),
        );
  const saved = preview.favoriteHeritageIds.includes(item.id);
  const toggle = () => {
    if (!preview.isAuthenticated)
      return navigate("/login", { state: { from: `/heritages/${item.id}` } });
    preview.toggleFavorite(item.id);
  };
  return (
    <div className="detail-page page-shell">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link to="/heritages">Di sản</Link>
        <span>/</span>
        <span>{item.name}</span>
      </nav>
      <header className="detail-hero">
        <div className="detail-image">
          <HeritageImage item={item} detail />
          <span className="image-caption">
            {app.mode === "preview"
              ? "Ảnh minh họa trong UI Preview"
              : "Ảnh từ backend"}
            {item.media[0] && !item.media[0].verified
              ? " · chưa xác minh tư liệu"
              : ""}
          </span>
        </div>
        <div className="detail-intro">
          <div className="detail-badges">
            {app.mode === "api" && <Badge tone="green">Dữ liệu backend</Badge>}
            {item.illustrative && <Badge tone="gold">Dữ liệu minh họa</Badge>}
            <Badge>{categoryLabels[item.category] || item.category}</Badge>
          </div>
          <h1>{item.name}</h1>
          <p className="detail-lead">{item.introduction}</p>
          <dl className="detail-facts">
            <div>
              <dt>Địa phương</dt>
              <dd>{item.province}</dd>
            </div>
            {item.address && (
              <div>
                <dt>Địa chỉ</dt>
                <dd>{item.address}</dd>
              </div>
            )}
            {item.period && (
              <div>
                <dt>Giai đoạn</dt>
                <dd>{item.period}</dd>
              </div>
            )}
          </dl>
          <div className="detail-actions">
            <Button
              onClick={() =>
                navigate(`/chat?heritage=${encodeURIComponent(item.id)}`)
              }
            >
              <MessageSquareText size={16} /> Hỏi về di sản
            </Button>
            {item.coordinates && (
              <Button
                tone="secondary"
                onClick={() =>
                  navigate(`/map?selected=${encodeURIComponent(item.id)}`)
                }
              >
                <MapPin size={16} /> Mở trên bản đồ
              </Button>
            )}
            {app.mode === "preview" && (
              <Button tone="ghost" onClick={toggle}>
                <Heart size={16} fill={saved ? "currentColor" : "none"} />{" "}
                {saved ? "Đã yêu thích" : "Yêu thích"}
              </Button>
            )}
            {app.mode === "api" && <ApiFavoriteButton id={item.id} text />}
          </div>
        </div>
      </header>
      {item.media[0] && (
        <p className="image-attribution">
          <span>{item.media[0].caption}</span>
          {app.mode === "preview" && (
            <a
              href="/heritages/credits.html"
              target="_blank"
              rel="noopener noreferrer"
            >
              Nguồn ảnh & giấy phép
            </a>
          )}
        </p>
      )}
      <div className="detail-columns">
        <article className="prose-panel">
          <section>
            <span className="eyebrow">CÂU CHUYỆN</span>
            <h2>Thông tin lịch sử</h2>
            {item.history ? (
              <p>{item.history}</p>
            ) : (
              <p className="muted">Chưa có nội dung lịch sử trong bản ghi.</p>
            )}
          </section>
          <section>
            <span className="eyebrow">GIÁ TRỊ</span>
            <h2>Văn hóa và cộng đồng</h2>
            {item.culturalValue ? (
              <p>{item.culturalValue}</p>
            ) : (
              <p className="muted">Chưa có nội dung văn hóa trong bản ghi.</p>
            )}
          </section>
        </article>
        <aside className="detail-side">
          <section className="panel">
            <h2>Vị trí</h2>
            {item.coordinates ? (
              <>
                <p>
                  <MapPin size={15} /> {item.coordinates.latitude.toFixed(5)},{" "}
                  {item.coordinates.longitude.toFixed(5)}
                </p>
                <Badge tone={item.coordinates.verified ? "green" : "gold"}>
                  {coordinateLabel(item)}
                </Badge>
                <small>{item.coordinates.verificationNote}</small>
              </>
            ) : (
              <p className="muted">Bản ghi không có tọa độ.</p>
            )}
          </section>
          <section className="panel">
            <h2>Nguồn thông tin</h2>
            {sources.length ? (
              <ul className="source-list">
                {sources.map((source) => (
                  <li key={source.id}>
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {source.title}
                    </a>
                    <small>
                      {source.publisher} ·{" "}
                      {source.verified
                        ? "đã xác minh metadata"
                        : "chưa xác minh"}
                    </small>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">Chưa liên kết nguồn metadata.</p>
            )}
            <p className="small warning-copy">
              <ShieldAlert size={14} /> Metadata nguồn không đồng nghĩa đã được
              ingest vào RAG.
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}
