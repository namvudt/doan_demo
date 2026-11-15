import { useMemo } from "react";
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
import type { PreviewHeritage } from "../preview/types";
import { Badge, Button, EmptyState, StatusCard } from "../ui/Ui";
import { ResilientImage } from "../ui/ResilientImage";

const categoryLabels: Record<string, string> = {
  monument: "Di tích lịch sử",
  temple: "Tín ngưỡng · tôn giáo",
  museum: "Bảo tàng",
  archaeology: "Khảo cổ",
};

function HeritageImage({
  item,
  detail = false,
}: {
  item: PreviewHeritage;
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

function HeritageCard({ item }: { item: PreviewHeritage }) {
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
        <Badge tone="gold">Minh họa</Badge>
      </Link>
      <div className="heritage-card-body">
        <div className="card-meta">
          <span>{categoryLabels[item.category]}</span>
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
          <button
            type="button"
            aria-label={saved ? "Bỏ yêu thích" : "Thêm yêu thích"}
            className={saved ? "favorite active" : "favorite"}
            onClick={favorite}
          >
            <Heart size={17} fill={saved ? "currentColor" : "none"} />
          </button>
        </div>
      </div>
    </article>
  );
}

export function HeritagesPage() {
  const app = useApp();
  const preview = usePreview();
  const [params, setParams] = useSearchParams();
  const query = params.get("q") || "";
  const province = params.get("province") || "";
  const category = params.get("category") || "";
  const provinces = useMemo(
    () => [...new Set(preview.heritages.map((item) => item.province))].sort(),
    [preview.heritages],
  );
  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("vi");
    return preview.heritages.filter((item) => {
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
  }, [preview.heritages, query, province, category]);

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
            Tìm hồ sơ minh họa theo địa phương và loại hình, rồi mở trong bản đồ
            hoặc hỏi cùng AI.
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

      {app.mode === "api" ? (
        <section className="api-catalog-state">
          <StatusCard
            kind="warning"
            title="Backend chưa có catalog di sản hoặc dữ liệu tọa độ"
          >
            Frontend không biến sample ảnh thành hồ sơ di sản. Danh sách dưới
            đây chỉ là sample thật từ <code>GET /api/v1/samples</code> để bắt
            đầu một run VQA.
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
              {filtered.length} hồ sơ minh họa
            </span>
          </section>
          {filtered.length ? (
            <section className="heritage-grid">
              {filtered.map((item) => (
                <HeritageCard item={item} key={item.id} />
              ))}
            </section>
          ) : (
            <EmptyState
              title="Không có kết quả phù hợp"
              icon={<Search size={27} />}
            >
              Thử bỏ bớt bộ lọc hoặc dùng từ khóa khác.
            </EmptyState>
          )}
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
  if (app.mode !== "preview") {
    return (
      <div className="page-shell narrow-page">
        <StatusCard kind="warning" title="Hồ sơ di sản không có trong API">
          Backend hiện chỉ cung cấp sample ảnh và run VQA.{" "}
          <Link to="/heritages">Xem sample thật</Link>.
        </StatusCard>
      </div>
    );
  }
  const item = preview.heritages.find((heritage) => heritage.id === heritageId);
  if (!item)
    return (
      <div className="page-shell">
        <EmptyState title="Không tìm thấy hồ sơ" icon={<Landmark size={28} />}>
          Hồ sơ có thể đã bị xóa trong phiên Preview.{" "}
          <Link to="/heritages">Về thư viện</Link>.
        </EmptyState>
      </div>
    );
  const sources = preview.contentSources.filter((source) =>
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
            Ảnh minh họa trong UI Preview
            {item.media[0] && !item.media[0].verified
              ? " · chưa xác minh tư liệu"
              : ""}
          </span>
        </div>
        <div className="detail-intro">
          <div className="detail-badges">
            <Badge tone="gold">Dữ liệu minh họa</Badge>
            <Badge>{categoryLabels[item.category]}</Badge>
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
            <Button onClick={() => navigate(`/chat?heritage=${item.id}`)}>
              <MessageSquareText size={16} /> Hỏi về di sản
            </Button>
            {item.coordinates && (
              <Button
                tone="secondary"
                onClick={() => navigate(`/map?selected=${item.id}`)}
              >
                <MapPin size={16} /> Mở trên bản đồ
              </Button>
            )}
            <Button tone="ghost" onClick={toggle}>
              <Heart size={16} fill={saved ? "currentColor" : "none"} />{" "}
              {saved ? "Đã yêu thích" : "Yêu thích"}
            </Button>
          </div>
        </div>
      </header>
      {item.media[0] && (
        <p className="image-attribution">
          <span>{item.media[0].caption}</span>
          <a
            href="/heritages/credits.html"
            target="_blank"
            rel="noopener noreferrer"
          >
            Nguồn ảnh & giấy phép
          </a>
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
              <p className="muted">
                Chưa có nội dung lịch sử trong bản ghi minh họa.
              </p>
            )}
          </section>
          <section>
            <span className="eyebrow">GIÁ TRỊ</span>
            <h2>Văn hóa và cộng đồng</h2>
            {item.culturalValue ? (
              <p>{item.culturalValue}</p>
            ) : (
              <p className="muted">
                Chưa có nội dung văn hóa trong bản ghi minh họa.
              </p>
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
                  {item.coordinates.verified
                    ? "Tọa độ đã xác minh"
                    : "Tọa độ minh họa"}
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
