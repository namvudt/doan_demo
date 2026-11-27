import { describe, expect, it } from "vitest";
import { createSchematicPoints, isValidMapPoint } from "../src/ui/mapGeometry";

describe("map coordinate and schematic safety", () => {
  it("keeps valid zero/boundary coordinates and rejects missing or invalid points", () => {
    expect(isValidMapPoint({ latitude: 0, longitude: 0 })).toBe(true);
    expect(isValidMapPoint({ latitude: -90, longitude: 180 })).toBe(true);
    for (const point of [
      { latitude: null, longitude: 105 },
      { latitude: 21, longitude: undefined },
      { latitude: Number.NaN, longitude: 105 },
      { latitude: 21, longitude: Number.POSITIVE_INFINITY },
      { latitude: 90.01, longitude: 105 },
      { latitude: 21, longitude: -180.01 },
    ]) {
      expect(isValidMapPoint(point)).toBe(false);
    }
  });

  it("preserves coordinate data and gives nearby points separate bounded targets", () => {
    const originals = Array.from({ length: 7 }, (_, index) => ({
      id: `nearby-${index}`,
      name: `Địa điểm ${index}`,
      latitude: 21.03,
      longitude: 105.84,
    }));
    const untouched = structuredClone(originals);
    const plotted = createSchematicPoints(originals);
    expect(originals).toEqual(untouched);
    expect(plotted.map((point) => point.id)).toEqual(
      originals.map((point) => point.id),
    );
    expect(new Set(plotted.map((point) => `${point.x},${point.y}`)).size).toBe(
      7,
    );
    for (const point of plotted) {
      expect(point.latitude).toBe(21.03);
      expect(point.longitude).toBe(105.84);
      expect(point.x).toBeGreaterThanOrEqual(12);
      expect(point.x).toBeLessThanOrEqual(88);
      expect(point.y).toBeGreaterThanOrEqual(15);
      expect(point.y).toBeLessThanOrEqual(82);
    }
  });

  it("keeps relative north/south direction and handles empty/single-point views", () => {
    expect(createSchematicPoints([])).toEqual([]);
    const one = createSchematicPoints([
      { id: "one", name: "Một địa điểm", latitude: 21, longitude: 105 },
    ]);
    expect(one[0].x).toBe(50);
    expect(one[0].y).toBe(50);
    const plotted = createSchematicPoints([
      { id: "north", name: "Phía Bắc", latitude: 21, longitude: 105 },
      { id: "south", name: "Phía Nam", latitude: 16, longitude: 108 },
    ]);
    expect(plotted[0].anchorY).toBeLessThan(plotted[1].anchorY);
  });
});
