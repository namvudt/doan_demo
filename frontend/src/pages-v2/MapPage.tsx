import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ChevronDown,
  ChevronUp,
  Layers3,
  List,
  Map,
  Maximize2,
  MessageSquareText,
  Minimize2,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
} from "lucide-react";
import { useApp } from "../app/AppContext";
import { usePreview } from "../preview/PreviewProvider";
import { MapCanvas } from "../ui/MapCanvas";
import { ResilientImage } from "../ui/ResilientImage";
import { Badge, Button, EmptyState, StatusCard } from "../ui/Ui";
import {
  coordinateLabel,
  toHeritageDisplay,
  useHeritageCatalog,
  type HeritageDisplay,
} from "../ui/useHeritageCatalog";

const mobileMap = () => window.matchMedia("(max-width: 760px)").matches;

export function MapPage() {
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
  const [listOnly, setListOnly] = useState(false);
  const [listCollapsed, setListCollapsed] = useState(mobileMap);
  const [detailsCollapsed, setDetailsCollapsed] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const expandButtonRef = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();
  const query = params.get("q") || "";
  const province = params.get("province") || "";
  const category = params.get("category") || "";
  const selectedId = params.get("selected") || undefined;
  const provinces = useMemo(
    () => [...new Set(records.map((item) => item.province))].sort(),
    [records],
  );
  const items = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("vi");
    return records.filter(
      (item) =>
        item.publicationStatus === "published" &&
        (!normalized ||
          `${item.name} ${item.province} ${item.tags.join(" ")}`
            .toLocaleLowerCase("vi")
            .includes(normalized)) &&
        (!province || item.province === province) &&
        (!category || item.category === category),
    );
  }, [records, query, province, category]);
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

  // Account for wrapped banners and browser text zoom without a fixed map height.
  useEffect(() => {
    const workspace = workspaceRef.current;
    const shell = workspace?.closest(".app-main-shell");
    if (!workspace || !shell) return;
    const chrome = shell.querySelectorAll<HTMLElement>(
      ":scope > .app-topbar, :scope > .preview-banner, :scope > .api-banner, :scope > .app-footer",
    );
    const measure = () => {
      const height = Array.from(chrome).reduce(
        (total, element) => total + element.getBoundingClientRect().height,
        0,
      );
      workspace.style.setProperty(
        "--map-shell-height",
        `${Math.ceil(height)}px`,
      );
    };
    measure();
    const observer = new ResizeObserver(measure);
    chrome.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [app.mode, catalog.supported]);

  // The expanded view is an in-app dialog; Leaflet stays in its original node.
  useEffect(() => {
    if (!expanded) return;
    const workspace = workspaceRef.current;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    expandButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setExpanded(false);
      }
      if (event.key !== "Tab" || !workspace) return;
      const controls = Array.from(
        workspace.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex="0"]',
        ),
      ).filter(
        (element) =>
          element.getClientRects().length > 0 &&
          getComputedStyle(element).visibility !== "hidden" &&
          !element.closest('[inert], [hidden], [aria-hidden="true"]'),
      );
      const first = controls[0];
      const last = controls.at(-1);
      if (!workspace.contains(document.activeElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first)?.focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected)
        previousFocus.focus({ preventScroll: true });
    };
  }, [expanded]);

  const select = (id: string) => {
    const next = new URLSearchParams(params);
    next.set("selected", id);
    if (query) next.set("q", query);
    else next.delete("q");
    setParams(next, { replace: true });
    if (mobileMap() && !listOnly) setListCollapsed(true);
  };
  const updateFilter = (name: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    next.delete("selected");
    setParams(next, { replace: true });
  };
  const toggleListOnly = () => {
    setListOnly((value) => !value);
    setListCollapsed(false);
  };
  if (app.mode === "api" && !catalog.supported)
    return (
      <div className="page-shell">
        <header className="page-heading">
          <div>
            <span className="eyebrow">BẢN ĐỒ</span>
            <h1>Bản đồ di sản</h1>
          </div>
        </header>
        <StatusCard
          kind={
            !app.capabilities && !app.capabilitiesError ? "loading" : "warning"
          }
          title={
            !app.capabilities && !app.capabilitiesError
              ? "Đang kiểm tra catalog di sản…"
              : "API chưa cung cấp catalog có tọa độ"
          }
        >
          {app.capabilitiesError ||
            "Chưa có dữ liệu bản đồ từ backend đã kết nối."}
        </StatusCard>
      </div>
    );
  return (
    <div
      ref={workspaceRef}
      className={`map-page-v2 ${listCollapsed ? "is-list-collapsed" : ""} ${listOnly ? "is-list-only" : ""} ${expanded ? "is-expanded" : ""} ${detailsCollapsed ? "is-detail-compact" : "is-detail-open"}`}
      role={expanded ? "dialog" : undefined}
      aria-modal={expanded || undefined}
      aria-label={expanded ? "Bản đồ di sản mở rộng" : undefined}
    >
      <header className="map-workspace-toolbar">
        <div className="map-workspace-heading">
          <span className="eyebrow">BẢN ĐỒ DI SẢN</span>
          <h1>Khám phá theo địa điểm</h1>
        </div>
        <div className="map-workspace-tools">
          <button
            type="button"
            className="map-layout-button"
            aria-label={listCollapsed ? "Mở danh sách" : "Thu gọn danh sách"}
            aria-controls="map-results-panel"
            aria-expanded={!listCollapsed}
            disabled={listOnly}
            onClick={() => setListCollapsed((value) => !value)}
          >
            {listCollapsed ? (
              <PanelLeftOpen size={17} />
            ) : (
              <PanelLeftClose size={17} />
            )}
            <span>{listCollapsed ? "Danh sách" : "Thu gọn"}</span>
          </button>
          <button
            type="button"
            className="map-layout-button"
            aria-label={listOnly ? "Hiện bản đồ" : "Chỉ danh sách"}
            aria-pressed={listOnly}
            onClick={toggleListOnly}
          >
            {listOnly ? <Map size={17} /> : <List size={17} />}
            <span>{listOnly ? "Hiện bản đồ" : "Chỉ danh sách"}</span>
          </button>
          <button
            ref={expandButtonRef}
            type="button"
            className="map-layout-button map-expand-button"
            aria-label={expanded ? "Thu gọn bản đồ" : "Mở rộng bản đồ"}
            aria-pressed={expanded}
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? <Minimize2 size={17} /> : <Maximize2 size={17} />}
            <span>{expanded ? "Thu nhỏ" : "Mở rộng"}</span>
          </button>
        </div>
      </header>
      <aside
        id="map-results-panel"
        className="map-list-panel"
        aria-label="Tìm và chọn địa điểm"
        hidden={listCollapsed}
      >
        <div className="map-list-intro">
          <strong>Tìm điểm đến của bạn</strong>
          <span>Chọn địa điểm để xem vị trí và câu chuyện.</span>
          {app.mode === "api" && <Badge tone="green">Dữ liệu backend</Badge>}
        </div>
        <label className="search-field">
          <Search size={17} />
          <span className="sr-only">Tìm trên bản đồ</span>
          <input
            value={query}
            onChange={(e) => updateFilter("q", e.target.value)}
            placeholder="Tên, địa phương hoặc chủ đề…"
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
        <div className="map-list-summary" aria-live="polite">
          <strong>{items.length} địa điểm</strong>
          <span>{located.length} có tọa độ</span>
        </div>
        <div className="map-results">
          {catalog.error && (
            <StatusCard kind="error" title="Không tải được dữ liệu bản đồ">
              {catalog.error}{" "}
              <Button
                tone="secondary"
                disabled={catalog.loading}
                onClick={catalog.refresh}
              >
                Thử lại
              </Button>
            </StatusCard>
          )}
          {catalog.hasMore && (
            <StatusCard
              kind="warning"
              title={`Đã tải ${records.length}/${catalog.total} hồ sơ`}
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
          {catalog.loading && !records.length ? (
            <StatusCard kind="loading" title="Đang tải địa điểm từ backend…" />
          ) : items.length ? (
            items.map((item, index) => (
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
                <span className="map-result-visual" aria-hidden="true">
                  <ResilientImage
                    src={item.media[0]?.url}
                    alt=""
                    className="map-result-image"
                    retryable={false}
                  />
                  <span className="result-pin">{index + 1}</span>
                </span>
                <span className="map-result-copy">
                  <strong>{item.name}</strong>
                  <small>{item.province}</small>
                  <small className="map-coordinate-note">
                    {coordinateLabel(item)}
                  </small>
                </span>
              </button>
            ))
          ) : !catalog.error ? (
            <EmptyState title="Không có kết quả" icon={<Search size={24} />}>
              Thử từ khóa khác hoặc xóa bộ lọc.
            </EmptyState>
          ) : null}
        </div>
      </aside>
      <section
        className="map-stage"
        aria-label="Vị trí di sản"
        hidden={listOnly}
      >
        <div className="map-surface">
          <MapCanvas
            items={mapItems}
            selectedId={selected?.id}
            focusSelected={Boolean(selectedId)}
            visible={!listOnly && located.length > 0}
            onSelect={select}
            onLocationError={(message) => app.notify(message, "error")}
          />
          {!located.length && (
            <div className="map-no-coordinates">
              {catalog.loading ? (
                <StatusCard kind="loading" title="Đang tải vị trí di sản…" />
              ) : catalog.error ? (
                <StatusCard kind="error" title="Không tải được vị trí di sản">
                  {catalog.error}
                </StatusCard>
              ) : (
                <EmptyState
                  title="Không có dữ liệu vị trí"
                  icon={<Layers3 size={27} />}
                >
                  Các hồ sơ phù hợp chưa có tọa độ hợp lệ. Thử thay đổi bộ lọc.
                </EmptyState>
              )}
            </div>
          )}
        </div>
        {selected && (
          <article className="map-preview-card" aria-label="Địa điểm đang chọn">
            <div className="map-selection-copy">
              <ResilientImage
                src={selected.media[0]?.url}
                alt={selected.media[0]?.alt || selected.name}
                className="map-selection-image"
                label={selected.name}
                retryable={false}
              />
              <div className="map-selection-text">
                <span className="eyebrow">ĐANG CHỌN · {selected.province}</span>
                <h2>{selected.name}</h2>
              </div>
              <button
                type="button"
                className="map-detail-toggle"
                aria-label={
                  detailsCollapsed
                    ? "Mở rộng thông tin địa điểm"
                    : "Thu gọn thông tin địa điểm"
                }
                aria-controls="map-selection-details"
                aria-expanded={!detailsCollapsed}
                onClick={() => setDetailsCollapsed((value) => !value)}
              >
                {detailsCollapsed ? (
                  <ChevronUp size={19} />
                ) : (
                  <ChevronDown size={19} />
                )}
              </button>
            </div>
            <div className="map-preview-actions">
              <Link
                to={`/heritages/${selected.id}`}
                className="button secondary"
              >
                Xem hồ sơ
              </Link>
              <Button
                onClick={() =>
                  navigate(`/chat?heritage=${encodeURIComponent(selected.id)}`)
                }
              >
                <MessageSquareText size={16} /> Hỏi trong Chat
              </Button>
            </div>
            <div
              id="map-selection-details"
              className="map-selection-details"
              hidden={detailsCollapsed}
            >
              <p>{selected.introduction}</p>
              <div className="card-meta">
                <Badge tone={selected.coordinates?.verified ? "green" : "gold"}>
                  {coordinateLabel(selected)}
                </Badge>
                <span>
                  {app.mode === "api"
                    ? "Dữ liệu backend"
                    : "Dữ liệu UI Preview"}
                </span>
              </div>
            </div>
          </article>
        )}
      </section>
    </div>
  );
}
