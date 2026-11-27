import { describe, expect, it } from "vitest";
import { getMapViewportRequest } from "../src/ui/mapViewport";

const hanoi = {
  id: "hanoi",
  name: "Hà Nội",
  latitude: 21.03,
  longitude: 105.85,
};
const hue = { id: "hue", name: "Huế", latitude: 16.46, longitude: 107.59 };

describe("map camera intent", () => {
  it("preserves a manually moved viewport across equivalent catalog renders", () => {
    const first = getMapViewportRequest([hanoi, hue], undefined, false);
    const refreshed = getMapViewportRequest(
      [
        { ...hue, name: "Tên mới" },
        { ...hanoi },
        { ...hanoi, id: "duplicate" },
      ],
      undefined,
      false,
    );
    expect(refreshed?.key).toBe(first?.key);
  });

  it("moves for an explicit selection or changed coordinate, but ignores labels", () => {
    const first = getMapViewportRequest([hanoi, hue], "hanoi", true);
    expect(first?.selected?.id).toBe("hanoi");
    expect(
      getMapViewportRequest([{ ...hanoi, name: "Updated" }, hue], "hanoi", true)
        ?.key,
    ).toBe(first?.key);
    expect(getMapViewportRequest([hanoi, hue], "hue", true)?.key).not.toBe(
      first?.key,
    );
    expect(
      getMapViewportRequest([{ ...hanoi, latitude: 21.04 }, hue], "hanoi", true)
        ?.key,
    ).not.toBe(first?.key);
  });

  it("fits filtered coordinates and does not invent a camera request for no results", () => {
    const all = getMapViewportRequest([hanoi, hue], "hanoi", false);
    expect(all?.selected).toBeUndefined();
    expect(getMapViewportRequest([hanoi], "hanoi", false)?.key).not.toBe(
      all?.key,
    );
    expect(getMapViewportRequest([], "missing", true)).toBeNull();
  });
});
