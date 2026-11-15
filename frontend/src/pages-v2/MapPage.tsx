import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Layers3, List, MapPin, MessageSquareText, Search } from "lucide-react";
import { useApp } from "../app/AppContext";
import { usePreview } from "../preview/PreviewProvider";
import { MapCanvas } from "../ui/MapCanvas";
import { ResilientImage } from "../ui/ResilientImage";
import { Badge, Button, EmptyState, StatusCard } from "../ui/Ui";

export function MapPage() {
  const app = useApp();
  const preview = usePreview();
  const [params, setParams] = useSearchParams();
  const [listOnly, setListOnly] = useState(false);
  const navigate = useNavigate();
  const query = params.get("q") || "";
  const province = params.get("province") || "";
  const category = params.get("category") || "";
  const selectedId = params.get("selected") || undefined;
  const provinces = useMemo(
    () => [...new Set(preview.heritages.map((item) => item.province))].sort(),
    [preview.heritages],
  );
  const items = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("vi");
    return preview.heritages.filter(
      (item) =>
        item.publicationStatus === "published" &&
        (!normalized ||
          `${item.name} ${item.province} ${item.tags.join(" ")}`
            .toLocaleLowerCase("vi")
            .includes(normalized)) &&
        (!province || item.province === province) &&
        (!category || item.category === category),
    );
  }, [preview.heritages, query, province, category]);
  const located = useMemo(
    () => items.filter((item) => item.coordinates),
    [items],
  );
  const mapItems = useMemo(
    () =>
      located.map((item) => ({
        id: item.id,
        name: item.name,
        latitude: item.coordinates?.latitude,
        longitude: item.coordinates?.longitude,
        coordinateVerified: item.coordinates?.verified,
      })),
    [located],
  );
  const selected = items.find((item) => item.id === selectedId) || items[0];
  const select = (id: string) => {
    const next = new URLSearchParams(params);
    next.set("selected", id);
    if (query) next.set("q", query);
    else next.delete("q");
    setParams(next, { replace: true });
  };
  const updateFilter = (name: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    next.delete("selected");
    setParams(next, { replace: true });
  };
  if (app.mode === "api")
    return (
      <div className="page-shell">
        <header className="page-heading">
          <div>
            <span className="eyebrow">BẢN ĐỒ</span>
            <h1>Bản đồ di sản</h1>
          </div>
        </header>
        <StatusCard kind="warning" title="API chưa cung cấp catalog có tọa độ">
          Không có marker nào được suy đoán từ tên sample, URL bản đồ hoặc câu
          trả lời AI. Chuyển sang UI Preview để xem luồng bản đồ mô phỏng.
        </StatusCard>
      </div>
    );
  return (
    <div className="map-page-v2">
      <aside className="map-list-panel">
        <header>
          <span className="eyebrow">BẢN ĐỒ DI SẢN</span>
          <h1>Khám phá theo địa điểm</h1>
          <p>
            Từ một địa điểm, mở ra một câu chuyện. Tìm điểm đến, xem vị trí hoặc
            tiếp tục khám phá cùng AI.
          </p>
        </header>
        <label className="search-field">
          <Search size={17} />
          <span className="sr-only">Tìm trên bản đồ</span>
          <input
            value={query}
            onChange={(e) => updateFilter("q", e.target.value)}
            placeholder="Tên hoặc địa phương…"
          />
        </label>
        <div className="map-filter-row">
          <label>
            <span className="sr-only">Lọc địa phương</span>
            <select
              value={province}
              onChange={(e) => updateFilter("province", e.target.value)}
            >
              <option value="">Mọi địa phương</option>
              {provinces.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </label>
          <label>
            <span className="sr-only">Lọc loại hình</span>
            <select
              value={category}
              onChange={(e) => updateFilter("category", e.target.value)}
            >
              <option value="">Mọi loại hình</option>
              <option value="monument">Di tích</option>
              <option value="temple">Tín ngưỡng</option>
              <option value="museum">Bảo tàng</option>
              <option value="archaeology">Khảo cổ</option>
            </select>
          </label>
        </div>
        {(query || province || category) && (
          <div className="map-filter-actions">
            <span>Đang lọc địa điểm</span>
            <button
              type="button"
              onClick={() => setParams({}, { replace: true })}
            >
              Xóa bộ lọc
            </button>
          </div>
        )}
        <div className="map-list-summary">
          <span>
            {items.length} kết quả · {located.length} có tọa độ
          </span>
          <button
            type="button"
            aria-pressed={listOnly}
            onClick={() => setListOnly((value) => !value)}
          >
            <List size={15} /> {listOnly ? "Hiện bản đồ" : "Chỉ danh sách"}
          </button>
        </div>
        <div className="map-results">
          {items.length ? (
            items.map((item) => (
              <button
                key={item.id}
                type="button"
                aria-pressed={item.id === selected?.id}
                className={
                  item.id === selected?.id
                    ? "map-result selected"
                    : "map-result"
                }
                onClick={() => select(item.id)}
              >
                <span className="result-pin">
                  <MapPin size={16} />
                </span>
                <span>
                  <strong>{item.name}</strong>
                  <small>
                    {item.province} ·{" "}
                    {item.coordinates
                      ? item.coordinates.verified
                        ? "tọa độ xác minh"
                        : "tọa độ minh họa"
                      : "chưa có tọa độ"}
                  </small>
                </span>
              </button>
            ))
          ) : (
            <EmptyState title="Không có kết quả" icon={<Search size={24} />}>
              Thử tìm bằng từ khóa khác.
            </EmptyState>
          )}
        </div>
      </aside>
      <section className={`map-stage ${listOnly ? "hidden-map" : ""}`}>
        {!listOnly && located.length ? (
          <MapCanvas
            items={mapItems}
            selectedId={selected?.id}
            focusSelected={Boolean(selectedId)}
            onSelect={select}
            onLocationError={(message) => app.notify(message, "error")}
          />
        ) : !listOnly ? (
          <EmptyState
            title="Không có dữ liệu vị trí"
            icon={<Layers3 size={27} />}
          >
            Các hồ sơ phù hợp chưa có tọa độ hợp lệ.
          </EmptyState>
        ) : null}
        {selected && (
          <article className="map-preview-card">
            <div className="map-selection-copy">
              <ResilientImage
                src={selected.media[0]?.url}
                alt={selected.media[0]?.alt || selected.name}
                className="map-selection-image"
                label={selected.name}
              />
              <div className="map-selection-text">
                <span className="eyebrow">ĐANG CHỌN</span>
                <h2>{selected.name}</h2>
                <p>{selected.introduction}</p>
                <div className="card-meta">
                  <Badge tone="gold">Minh họa</Badge>
                  <span>{selected.province}</span>
                </div>
              </div>
            </div>
            <div className="map-preview-actions">
              <Link
                to={`/heritages/${selected.id}`}
                className="button secondary"
              >
                Xem hồ sơ
              </Link>
              <Button onClick={() => navigate(`/chat?heritage=${selected.id}`)}>
                <MessageSquareText size={16} /> Hỏi trong Chat
              </Button>
            </div>
          </article>
        )}
      </section>
    </div>
  );
}
