type MapProviderInput = {
  provider?: string;
  tileUrl?: string;
  mapboxToken?: string;
  development: boolean;
};

export type MapProviderConfig = {
  id: "mapbox" | "osm" | "custom" | "unconfigured";
  label: string;
  tileUrl: string;
  attribution: string;
  tileSize: number;
  zoomOffset: number;
  maxNativeZoom?: number;
  logo?: { src: string; href: string; alt: string };
  message?: string;
};

const osmCredit =
  '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>';

export function getMapProviderConfig(
  input: MapProviderInput,
): MapProviderConfig {
  const provider = input.provider?.trim().toLowerCase() || "auto";
  const unconfigured = (message: string): MapProviderConfig => ({
    id: "unconfigured",
    label: "Sơ đồ vị trí",
    tileUrl: "",
    attribution: "",
    tileSize: 256,
    zoomOffset: 0,
    message,
  });
  if (provider === "mapbox") {
    const token = input.mapboxToken?.trim();
    if (!token)
      return unconfigured(
        "Chưa có token Mapbox. Điền public token vào cấu hình local để thử nền bản đồ.",
      );
    if (!token.startsWith("pk.") || /\s/.test(token))
      return unconfigured(
        "Mapbox cần public token dạng pk. cho trình duyệt. Kiểm tra cấu hình local.",
      );
    return {
      id: "mapbox",
      label: "Mapbox",
      tileUrl: `https://api.mapbox.com/styles/v1/mapbox/streets-v12/tiles/512/{z}/{x}/{y}?access_token=${encodeURIComponent(token)}`,
      attribution:
        '<a href="https://www.mapbox.com/about/maps/" target="_blank" rel="noopener noreferrer">&copy; Mapbox</a> · ' +
        osmCredit +
        ' · <a href="https://apps.mapbox.com/feedback/" target="_blank" rel="noopener noreferrer">Improve this map</a>',
      // Mapbox's native 512px tiles cover the same area one zoom level lower.
      tileSize: 512,
      zoomOffset: -1,
      logo: {
        src: "/mapbox-logo-white.svg",
        href: "https://www.mapbox.com/about/maps/",
        alt: "Mapbox",
      },
    };
  }
  if (!["auto", "custom"].includes(provider))
    return unconfigured(
      "Nguồn bản đồ chưa được hỗ trợ. Kiểm tra cấu hình local.",
    );
  const tileUrl =
    input.tileUrl === undefined
      ? input.development
        ? "https://tile.openstreetmap.de/{z}/{x}/{y}.png"
        : "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      : input.tileUrl;
  let host = "";
  try {
    host = new URL(tileUrl).hostname;
  } catch {
    // An empty URL intentionally selects the coordinate diagram.
  }
  const osmDe = host === "tile.openstreetmap.de";
  const carto = host === "basemaps.cartocdn.com" || host.endsWith(".basemaps.cartocdn.com");
  const esri = host === "server.arcgisonline.com";
  return {
    id: host === "tile.openstreetmap.org" || osmDe ? "osm" : "custom",
    label: "Bản đồ trực tuyến",
    tileUrl,
    attribution: esri
      ? 'Tiles &copy; <a href="https://www.esri.com/" target="_blank" rel="noopener noreferrer">Esri</a>'
      : osmCredit +
        (osmDe
          ? ' · Tiles: <a href="https://www.openstreetmap.de/" target="_blank" rel="noopener noreferrer">OpenStreetMap Deutschland</a>'
          : carto
            ? ' · &copy; <a href="https://carto.com/attributions" target="_blank" rel="noopener noreferrer">CARTO</a>'
            : ""),
    tileSize: 256,
    zoomOffset: 0,
    ...(osmDe ? { maxNativeZoom: 18 } : esri ? { maxNativeZoom: 18 } : {}),
  };
}
