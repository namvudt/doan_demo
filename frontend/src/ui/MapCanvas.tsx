import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import {
  Compass,
  LocateFixed,
  Map,
  Maximize2,
  Minus,
  Plus,
  RefreshCw,
  Sparkles,
  WifiOff,
} from "lucide-react";
import { createSchematicPoints, isValidMapPoint } from "./mapGeometry";
import { getMapViewportRequest } from "./mapViewport";
import { getMapProviderConfig } from "./mapProvider";
import "./map-experience.css";

export type MapItem = {
  id: string;
  name: string;
  latitude?: number | null;
  longitude?: number | null;
  coordinateVerified?: boolean;
};

type Props = {
  items: MapItem[];
  selectedId?: string;
  focusSelected?: boolean;
  visible?: boolean;
  onSelect: (id: string) => void;
  onTileFailure?: () => void;
  onLocationError?: (message: string) => void;
};

const provider = getMapProviderConfig({
  provider: import.meta.env.VITE_MAP_PROVIDER,
  tileUrl: import.meta.env.VITE_MAP_TILE_URL,
  mapboxToken: import.meta.env.VITE_MAPBOX_ACCESS_TOKEN,
  development: import.meta.env.DEV,
});
const tileUrl = provider.tileUrl;

export function MapCanvas({
  items,
  selectedId,
  focusSelected = true,
  visible = true,
  onSelect,
  onTileFailure,
  onLocationError,
}: Props) {
  const element = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  const locationMarker = useRef<L.CircleMarker | null>(null);
  const markersById = useRef(
    new globalThis.Map<
      string,
      { marker: L.Marker; item: MapItem; selected: boolean }
    >(),
  );
  const tilesHealthy = useRef(false);
  const visibleRef = useRef(visible);
  visibleRef.current = visible;
  const selectRef = useRef(onSelect);
  const failureRef = useRef(onTileFailure);
  const manualSchematic = useRef(false);
  selectRef.current = onSelect;
  failureRef.current = onTileFailure;
  const [mode, setMode] = useState<"loading" | "online" | "schematic">(
    tileUrl ? "loading" : "schematic",
  );
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const [attempt, setAttempt] = useState(0);
  const [hasOnlineTiles, setHasOnlineTiles] = useState(false);
  const [locating, setLocating] = useState(false);
  const [locationMessage, setLocationMessage] = useState("");
  const validItems = useMemo(() => items.filter(isValidMapPoint), [items]);
  const itemsRef = useRef(validItems);
  itemsRef.current = validItems;
  const viewportRequest = useMemo(
    () => getMapViewportRequest(validItems, selectedId, focusSelected),
    [validItems, selectedId, focusSelected],
  );
  const viewportRequestRef = useRef(viewportRequest);
  viewportRequestRef.current = viewportRequest;
  const viewportKey = viewportRequest?.key;
  const appliedViewportKey = useRef<string | undefined>(undefined);
  const schematic = useMemo(
    () => createSchematicPoints(validItems),
    [validItems],
  );

  const fitVisible = useCallback(() => {
    const instance = map.current;
    const points = itemsRef.current;
    if (!instance || !points.length) return;
    instance.stop();
    if (points.length === 1) {
      instance.setView([points[0].latitude, points[0].longitude], 13, {
        animate: false,
      });
    } else {
      const size = instance.getSize();
      instance.fitBounds(
        L.latLngBounds(points.map((item) => [item.latitude, item.longitude])),
        {
          // Keep the usable map area positive in compact and mobile layouts.
          paddingTopLeft: [
            Math.min(56, size.x * 0.09),
            Math.min(84, size.y * 0.16),
          ],
          paddingBottomRight: [
            Math.min(48, size.x * 0.08),
            Math.min(164, size.y * 0.36),
          ],
          maxZoom: 13,
          animate: false,
        },
      );
    }
  }, []);

  useEffect(() => {
    if (!element.current) return;
    const instance = L.map(element.current, {
      attributionControl: true,
      zoomControl: false,
      // Leaflet's CSS zoom timeout cannot be cancelled on route unmount.
      // Controls use cancellable flyTo; tile transforms stay smooth during it.
      zoomAnimation: false,
      fadeAnimation: !window.matchMedia("(prefers-reduced-motion: reduce)")
        .matches,
      markerZoomAnimation: false,
      wheelDebounceTime: 80,
      wheelPxPerZoomLevel: 100,
      minZoom: 2,
      maxZoom: 19,
    });
    map.current = instance;
    layer.current = L.layerGroup().addTo(instance);
    const markerEntries = markersById.current;
    let resizeFrame = 0;
    const observer = new ResizeObserver(() => {
      if (resizeFrame || !visibleRef.current) return;
      resizeFrame = requestAnimationFrame(() => {
        resizeFrame = 0;
        // Raw pane compensation preserves the geographic center on resize.
        // No animation or camera refocus is started by layout changes.
        if (visibleRef.current)
          instance.invalidateSize({
            animate: false,
            pan: true,
            debounceMoveend: true,
          });
      });
    });
    observer.observe(element.current);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(resizeFrame);
      instance.stop();
      instance.remove();
      markerEntries.clear();
      appliedViewportKey.current = undefined;
      map.current = null;
      layer.current = null;
      locationMarker.current = null;
    };
  }, []);

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    if (!visible) {
      instance.stop();
      return;
    }
    const frame = requestAnimationFrame(() => {
      instance.invalidateSize({
        animate: false,
        pan: true,
        debounceMoveend: true,
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [visible]);

  useEffect(() => {
    const instance = map.current;
    const request = viewportRequestRef.current;
    if (
      !instance ||
      !visible ||
      !request ||
      appliedViewportKey.current === request.key
    )
      return;
    appliedViewportKey.current = request.key;
    if (request.selected) {
      const reducedMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)",
      ).matches;
      const selected = request.selected;
      instance.stop();
      if (reducedMotion || modeRef.current !== "online")
        instance.setView([selected.latitude, selected.longitude], 14, {
          animate: false,
        });
      else
        instance.flyTo([selected.latitude, selected.longitude], 14, {
          duration: 0.45,
        });
    } else fitVisible();
  }, [viewportKey, visible, fitVisible]);

  // A retry replaces only the provider layer. Camera and marker instances survive.
  // Camera setup runs first, so initial tiles belong to the intended viewport.
  useEffect(() => {
    const instance = map.current;
    if (!instance || !tileUrl) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let fallbackFrame = 0;
    let disposed = false;
    let loaded = 0;
    let failed = 0;
    tilesHealthy.current = false;
    setHasOnlineTiles(false);
    const tiles = L.tileLayer(tileUrl, {
      attribution: provider.attribution,
      maxZoom: 19,
      tileSize: provider.tileSize,
      zoomOffset: provider.zoomOffset,
      ...(provider.maxNativeZoom
        ? { maxNativeZoom: provider.maxNativeZoom }
        : {}),
      // Retain nearby tiles already visited; never prefetch outside the viewport.
      updateWhenIdle: true,
      updateWhenZooming: false,
      keepBuffer: L.Browser.mobile ? 2 : 3,
    });
    const showSchematic = () => {
      if (disposed || loaded || fallbackFrame) return;
      // Leaflet still reads its map after emitting `load`. Detach the provider
      // after that callback stack, and cancel the work if the route unmounts.
      fallbackFrame = requestAnimationFrame(() => {
        fallbackFrame = 0;
        if (disposed || loaded) return;
        instance.stop();
        setMode("schematic");
        tiles.off();
        tiles.remove();
        failureRef.current?.();
        if (timer) clearTimeout(timer);
      });
    };
    tiles.on("loading", () => {
      // Background pan/zoom requests do not reset a healthy map's status.
      if (!loaded && !timer) timer = setTimeout(showSchematic, 10_000);
    });
    tiles.on("tileload", () => {
      loaded += 1;
      if (disposed || tilesHealthy.current) return;
      tilesHealthy.current = true;
      setHasOnlineTiles(true);
      if (!manualSchematic.current) setMode("online");
      if (timer) clearTimeout(timer);
    });
    tiles.on("tileerror", () => {
      failed += 1;
    });
    tiles.on("load", () => {
      if (!loaded && failed) showSchematic();
    });
    tiles.addTo(instance);
    return () => {
      disposed = true;
      if (timer) clearTimeout(timer);
      cancelAnimationFrame(fallbackFrame);
      tiles.off();
      tiles.remove();
    };
  }, [attempt]);

  useEffect(() => {
    const markers = layer.current;
    if (!markers) return;
    const entries = markersById.current;
    const ids = new Set(validItems.map((item) => item.id));
    for (const [id, entry] of entries) {
      if (ids.has(id)) continue;
      entry.marker.off();
      markers.removeLayer(entry.marker);
      entries.delete(id);
    }
    for (const item of validItems) {
      const selected = item.id === selectedId;
      let entry = entries.get(item.id);
      if (!entry) {
        const icon = L.divIcon({
          className: `heritage-pin ${selected ? "selected" : ""} ${item.coordinateVerified ? "verified" : "illustrative"}`,
          html: '<span aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 20h18M5 18h14M7 16V9h10v7M4 9h16L12 3zM10 16v-4h4v4"/></svg></span>',
          iconSize: [38, 44],
          iconAnchor: [19, 44],
        });
        const marker = L.marker([item.latitude, item.longitude], {
          icon,
          title: item.name,
          keyboard: true,
          alt: item.name,
          zIndexOffset: selected ? 1000 : 0,
        }).addTo(markers);
        const tooltip = document.createElement("span");
        tooltip.textContent = item.name;
        marker.bindTooltip(tooltip, { direction: "top", offset: [0, -40] });
        marker.on("click", () => selectRef.current(item.id));
        entry = { marker, item, selected };
        entries.set(item.id, entry);
      } else {
        if (
          entry.item.latitude !== item.latitude ||
          entry.item.longitude !== item.longitude
        )
          entry.marker.setLatLng([item.latitude, item.longitude]);
        if (entry.item.name !== item.name) {
          const tooltip = document.createElement("span");
          tooltip.textContent = item.name;
          entry.marker.setTooltipContent(tooltip);
          entry.marker.options.title = item.name;
          entry.marker.options.alt = item.name;
        }
        if (entry.selected !== selected)
          entry.marker.setZIndexOffset(selected ? 1000 : 0);
        entry.item = item;
        entry.selected = selected;
      }
      const node = entry.marker.getElement();
      if (node) {
        node.classList.toggle("selected", selected);
        node.classList.toggle("verified", Boolean(item.coordinateVerified));
        node.classList.toggle("illustrative", !item.coordinateVerified);
        node.setAttribute("aria-pressed", String(selected));
        node.setAttribute("aria-label", item.name);
        node.title = item.name;
      }
    }
  }, [validItems, selectedId, visible]);

  const zoomBy = (delta: number) => {
    const instance = map.current;
    if (!instance || !appliedViewportKey.current) return;
    const zoom = Math.max(
      instance.getMinZoom(),
      Math.min(instance.getMaxZoom(), Math.round(instance.getZoom()) + delta),
    );
    const center = instance.getCenter();
    instance.stop();
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches)
      instance.setView(center, zoom, { animate: false });
    else instance.flyTo(center, zoom, { duration: 0.25 });
  };

  const locate = () => {
    if (!navigator.geolocation) {
      onLocationError?.("Trình duyệt không hỗ trợ định vị.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setLocating(false);
        setLocationMessage(
          `Vị trí của bạn: ${coords.latitude.toFixed(3)}, ${coords.longitude.toFixed(3)}.`,
        );
        const instance = map.current;
        if (!instance) return;
        locationMarker.current?.remove();
        locationMarker.current = L.circleMarker(
          [coords.latitude, coords.longitude],
          {
            radius: 8,
            color: "#f6e0a7",
            fillColor: "#4b9c82",
            fillOpacity: 1,
          },
        ).addTo(instance);
        instance.setView([coords.latitude, coords.longitude], 13, {
          animate: false,
        });
      },
      () => {
        setLocating(false);
        onLocationError?.(
          "Không lấy được vị trí. Bạn vẫn có thể khám phá bằng danh sách địa điểm.",
        );
      },
      { timeout: 10_000 },
    );
  };

  return (
    <div
      className="map-canvas-shell map-canvas map-experience"
      data-map-mode={mode}
      data-map-provider={provider.id}
      aria-hidden={!visible}
      inert={!visible}
      style={{ visibility: visible ? undefined : "hidden" }}
    >
      <div
        ref={element}
        // Leaflet owns additional classes on this node; keep React's class stable.
        className="map-leaflet-canvas"
        style={{ visibility: mode === "schematic" ? "hidden" : undefined }}
        aria-label="Bản đồ tương tác các di sản"
        aria-hidden={mode === "schematic" || !visible}
        inert={mode === "schematic" || !visible}
      />
      {provider.logo && mode !== "schematic" && (
        <a
          className="map-provider-logo"
          href={provider.logo.href}
          target="_blank"
          rel="noopener noreferrer"
        >
          <img
            src={provider.logo.src}
            alt={provider.logo.alt}
            width="89"
            height="20"
          />
        </a>
      )}
      {mode === "schematic" ? (
        <section
          className="offline-atlas"
          aria-label="Sơ đồ vị trí di sản"
          data-testid="offline-map"
        >
          <div className="atlas-heading">
            <div>
              <span className="atlas-status">
                <WifiOff size={13} /> Sơ đồ ngoại tuyến
              </span>
              <h2>Khám phá không gián đoạn</h2>
              <p>Chọn một điểm đến để tiếp tục hành trình của bạn.</p>
              {provider.message && (
                <span className="map-provider-message" role="status">
                  {provider.message}
                </span>
              )}
            </div>
            {tileUrl && (
              <button
                type="button"
                className="atlas-retry"
                onClick={() => {
                  manualSchematic.current = false;
                  if (tilesHealthy.current) {
                    setMode("online");
                    return;
                  }
                  setMode("loading");
                  setAttempt((value) => value + 1);
                }}
              >
                <RefreshCw size={14} />{" "}
                {hasOnlineTiles ? "Quay lại bản đồ" : "Thử tải bản đồ"}
              </button>
            )}
          </div>
          <div className="atlas-chart">
            <svg
              className="atlas-grid"
              viewBox="0 0 900 500"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              <defs>
                <pattern
                  id="atlas-dots"
                  width="30"
                  height="30"
                  patternUnits="userSpaceOnUse"
                >
                  <circle cx="1" cy="1" r="1" fill="currentColor" />
                </pattern>
                <radialGradient id="atlas-glow">
                  <stop stopColor="#44634d" stopOpacity=".55" />
                  <stop offset="1" stopColor="#10251e" stopOpacity="0" />
                </radialGradient>
              </defs>
              <rect width="900" height="500" fill="url(#atlas-glow)" />
              <rect width="900" height="500" fill="url(#atlas-dots)" />
              <path
                d="M20 370C220 410 160 140 390 170S620 430 900 250M0 320C220 360 200 90 410 120S660 360 900 200M70 430C300 490 200 200 430 220S690 480 900 330"
                className="atlas-contour"
              />
              {schematic.map((point) => (
                <g key={point.id}>
                  <line
                    x1={point.anchorX * 9}
                    y1={point.anchorY * 5}
                    x2={point.x * 9}
                    y2={point.y * 5}
                    className="atlas-leader"
                  />
                  <circle
                    cx={point.anchorX * 9}
                    cy={point.anchorY * 5}
                    r="3"
                    className="atlas-anchor"
                  />
                </g>
              ))}
            </svg>
            <span className="atlas-north">
              <Compass size={16} /> BẮC
            </span>
            {schematic.map((point, index) => (
              <button
                type="button"
                key={point.id}
                className={`atlas-point ${point.id === selectedId ? "is-selected" : ""}`}
                style={{ left: `${point.x}%`, top: `${point.y}%` }}
                aria-label={`Chọn ${point.name} trên sơ đồ`}
                aria-pressed={point.id === selectedId}
                title={`${point.name} · ${point.latitude.toFixed(4)}, ${point.longitude.toFixed(4)}`}
                onClick={() => onSelect(point.id)}
              >
                <span>{index + 1}</span>
                <strong>{point.name}</strong>
              </button>
            ))}
          </div>
          <p className="atlas-caption">
            <Sparkles size={13} /> Sơ đồ theo tọa độ minh họa; các điểm gần nhau
            được giãn để dễ chọn. Không dùng để dẫn đường.
          </p>
        </section>
      ) : (
        <div className="map-live-status" role="status">
          <Map size={13} />{" "}
          {mode === "loading" ? "Đang mở bản đồ…" : provider.label}
          <button
            type="button"
            onClick={() => {
              manualSchematic.current = true;
              map.current?.stop();
              setMode("schematic");
            }}
          >
            Xem sơ đồ
          </button>
        </div>
      )}
      <div
        className={`map-controls ${mode === "schematic" ? "schematic-controls" : ""}`}
        aria-label="Điều khiển bản đồ"
      >
        {mode !== "schematic" && (
          <>
            <button
              type="button"
              aria-label="Phóng to"
              onClick={() => zoomBy(1)}
            >
              <Plus size={18} />
            </button>
            <button
              type="button"
              aria-label="Thu nhỏ"
              onClick={() => zoomBy(-1)}
            >
              <Minus size={18} />
            </button>
            <span />
            <button
              type="button"
              aria-label="Xem tất cả địa điểm"
              onClick={fitVisible}
            >
              <Maximize2 size={17} />
            </button>
            <button
              type="button"
              aria-label="Xem toàn Việt Nam"
              onClick={() =>
                map.current?.fitBounds(
                  [
                    [8.1, 102],
                    [23.6, 110],
                  ],
                  { padding: [24, 24] },
                )
              }
            >
              <Compass size={18} />
            </button>
          </>
        )}
        <button
          type="button"
          aria-label="Dùng vị trí của tôi"
          disabled={locating}
          onClick={locate}
          title="Chỉ định vị khi bạn chọn"
        >
          <LocateFixed size={18} className={locating ? "is-locating" : ""} />
        </button>
      </div>
      {locationMessage && (
        <span className="map-location-message" role="status">
          {locationMessage}
        </span>
      )}
    </div>
  );
}
