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
  onSelect: (id: string) => void;
  onTileFailure?: () => void;
  onLocationError?: (message: string) => void;
};

const configuredTileUrl = import.meta.env.VITE_MAP_TILE_URL;
const tileUrl =
  configuredTileUrl === undefined
    ? import.meta.env.DEV
      ? "https://tile.openstreetmap.de/{z}/{x}/{y}.png"
      : "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    : configuredTileUrl;
const usesOsmDe = (() => {
  try {
    return new URL(tileUrl).hostname === "tile.openstreetmap.de";
  } catch {
    return false;
  }
})();

export function MapCanvas({
  items,
  selectedId,
  focusSelected = true,
  onSelect,
  onTileFailure,
  onLocationError,
}: Props) {
  const element = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  const locationMarker = useRef<L.CircleMarker | null>(null);
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
  const [locating, setLocating] = useState(false);
  const [locationMessage, setLocationMessage] = useState("");
  const validItems = useMemo(() => items.filter(isValidMapPoint), [items]);
  const schematic = useMemo(
    () => createSchematicPoints(validItems),
    [validItems],
  );

  const fitVisible = useCallback(() => {
    const instance = map.current;
    if (!instance || !validItems.length) return;
    instance.stop();
    if (validItems.length === 1) {
      instance.setView([validItems[0].latitude, validItems[0].longitude], 13, {
        animate: false,
      });
    } else {
      instance.fitBounds(
        L.latLngBounds(
          validItems.map((item) => [item.latitude, item.longitude]),
        ),
        {
          paddingTopLeft: [70, 100],
          paddingBottomRight: [60, 200],
          maxZoom: 13,
          animate: false,
        },
      );
    }
  }, [validItems]);

  useEffect(() => {
    if (!element.current) return;
    const instance = L.map(element.current, {
      attributionControl: true,
      zoomControl: false,
      // CSS zoom transitions can finish after a React route unmounts. Selection
      // uses the cancellable flyTo path below; hidden maps never animate.
      zoomAnimation: false,
      fadeAnimation: false,
      markerZoomAnimation: false,
      minZoom: 2,
      maxZoom: 19,
    }).setView([16.4, 107.6], 5);
    map.current = instance;
    layer.current = L.layerGroup().addTo(instance);
    let timer: ReturnType<typeof setTimeout> | undefined;
    let disposed = false;
    if (tileUrl) {
      let loaded = 0;
      let failed = 0;
      const tiles = L.tileLayer(tileUrl, {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>' +
          (usesOsmDe
            ? ' · Tiles: <a href="https://www.openstreetmap.de/" target="_blank" rel="noopener noreferrer">OpenStreetMap Deutschland</a>'
            : ""),
        maxZoom: 19,
        ...(usesOsmDe ? { maxNativeZoom: 18 } : {}),
      });
      const showSchematic = () => {
        if (disposed || loaded) return;
        instance.stop();
        setMode("schematic");
        tiles.off();
        tiles.remove();
        failureRef.current?.();
        if (timer) clearTimeout(timer);
      };
      tiles.on("tileload", () => {
        loaded += 1;
        if (!disposed && !manualSchematic.current) setMode("online");
        if (timer) clearTimeout(timer);
      });
      tiles.on("tileerror", () => {
        failed += 1;
        if (failed >= 2) showSchematic();
      });
      tiles.addTo(instance);
      timer = setTimeout(showSchematic, 7_000);
    }
    const observer = new ResizeObserver(() => instance.invalidateSize());
    observer.observe(element.current);
    return () => {
      disposed = true;
      if (timer) clearTimeout(timer);
      observer.disconnect();
      instance.stop();
      instance.remove();
      map.current = null;
      layer.current = null;
      locationMarker.current = null;
    };
  }, [attempt]);

  useEffect(() => {
    const markers = layer.current;
    if (!markers) return;
    markers.clearLayers();
    for (const item of validItems) {
      const selected = item.id === selectedId;
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
      }).addTo(markers);
      marker.getElement()?.setAttribute("aria-pressed", String(selected));
      const tooltip = document.createElement("span");
      tooltip.textContent = item.name;
      marker.bindTooltip(tooltip, { direction: "top", offset: [0, -40] });
      marker.on("click", () => selectRef.current(item.id));
    }
  }, [validItems, selectedId, attempt]);

  useEffect(() => {
    const selected = validItems.find((item) => item.id === selectedId);
    if (focusSelected && selected) {
      const reducedMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)",
      ).matches;
      map.current?.stop();
      if (reducedMotion || modeRef.current !== "online")
        map.current?.setView([selected.latitude, selected.longitude], 14, {
          animate: false,
        });
      else
        map.current?.flyTo([selected.latitude, selected.longitude], 14, {
          duration: 0.6,
        });
    } else fitVisible();
  }, [fitVisible, validItems, selectedId, focusSelected, attempt]);

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
    >
      <div
        ref={element}
        className={`map-leaflet-canvas ${mode === "schematic" ? "is-covered" : ""}`}
        aria-label="Bản đồ tương tác các di sản"
        aria-hidden={mode === "schematic"}
        inert={mode === "schematic"}
      />
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
            </div>
            {tileUrl && (
              <button
                type="button"
                className="atlas-retry"
                onClick={() => {
                  manualSchematic.current = false;
                  setMode("loading");
                  setAttempt((value) => value + 1);
                }}
              >
                <RefreshCw size={14} /> Thử tải bản đồ
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
          {mode === "loading" ? "Đang mở bản đồ…" : "Bản đồ trực tuyến"}
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
              onClick={() => map.current?.zoomIn()}
            >
              <Plus size={18} />
            </button>
            <button
              type="button"
              aria-label="Thu nhỏ"
              onClick={() => map.current?.zoomOut()}
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
