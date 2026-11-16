export type LocatedMapPoint = {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
};

export function isValidMapPoint<
  T extends { latitude?: number | null; longitude?: number | null },
>(item: T): item is T & { latitude: number; longitude: number } {
  return (
    typeof item.latitude === "number" &&
    Number.isFinite(item.latitude) &&
    item.latitude >= -90 &&
    item.latitude <= 90 &&
    typeof item.longitude === "number" &&
    Number.isFinite(item.longitude) &&
    item.longitude >= -180 &&
    item.longitude <= 180
  );
}

/** A bounded coordinate diagram, deliberately not a geographic boundary map. */
export function createSchematicPoints<T extends LocatedMapPoint>(items: T[]) {
  if (!items.length) return [];
  const latitudes = items.map((item) => item.latitude);
  const longitudes = items.map((item) => item.longitude);
  const south = Math.min(...latitudes);
  const north = Math.max(...latitudes);
  const west = Math.min(...longitudes);
  const east = Math.max(...longitudes);
  const latRange = Math.max(north - south, 0.08);
  const lngRange = Math.max(east - west, 0.08);
  const plotted: Array<
    T & { anchorX: number; anchorY: number; x: number; y: number }
  > = [];
  for (const item of items) {
    const anchorX =
      east === west ? 50 : 24 + ((item.longitude - west) / lngRange) * 48;
    const anchorY =
      north === south ? 50 : 22 + ((north - item.latitude) / latRange) * 52;
    let x = anchorX;
    let y = anchorY;
    for (let attempt = 0; attempt < 36; attempt += 1) {
      if (
        !plotted.some(
          (point) => Math.hypot((point.x - x) * 1.7, point.y - y) < 15,
        )
      )
        break;
      const ring = Math.floor(attempt / 8) + 1;
      const angle = ((attempt % 8) / 8) * Math.PI * 2;
      x = Math.min(88, Math.max(12, anchorX + Math.cos(angle) * ring * 12));
      y = Math.min(82, Math.max(15, anchorY + Math.sin(angle) * ring * 16));
    }
    plotted.push({ ...item, anchorX, anchorY, x, y });
  }
  return plotted;
}
