import { describe, expect, it } from "vitest";
import { getMapProviderConfig } from "../src/ui/mapProvider";

describe("map provider configuration", () => {
  it("uses the existing local and production defaults when no provider is chosen", () => {
    expect(getMapProviderConfig({ development: true }).tileUrl).toContain(
      "tile.openstreetmap.de",
    );
    expect(getMapProviderConfig({ development: false }).tileUrl).toContain(
      "tile.openstreetmap.org",
    );
  });

  it("keeps an explicit empty tile URL offline and custom fixture URLs unchanged", () => {
    expect(
      getMapProviderConfig({ development: true, tileUrl: "" }).tileUrl,
    ).toBe("");
    const fixture = "https://tiles.test/{z}/{x}/{y}.png";
    expect(
      getMapProviderConfig({
        development: true,
        provider: "custom",
        tileUrl: fixture,
      }),
    ).toMatchObject({
      id: "custom",
      tileUrl: fixture,
      tileSize: 256,
      zoomOffset: 0,
    });
  });

  it("uses Mapbox's 512px geometry and branding even when the old tile URL exists", () => {
    const config = getMapProviderConfig({
      development: true,
      provider: "mapbox",
      mapboxToken: "pk.fixture-only",
      tileUrl: "https://tile.openstreetmap.de/{z}/{x}/{y}.png",
    });
    expect(config).toMatchObject({
      id: "mapbox",
      tileSize: 512,
      zoomOffset: -1,
    });
    expect(config.tileUrl).toContain("/mapbox/streets-v12/tiles/512/");
    expect(config.logo?.src).toBe("/mapbox-logo-white.svg");
    expect(config.attribution).toContain("&copy; Mapbox");
    expect(config.attribution).toContain("OpenStreetMap");
    expect(config.attribution).toContain("Improve this map");
  });

  it("sends no tile requests when a Mapbox token is missing or is a secret token", () => {
    for (const token of [
      undefined,
      "",
      "sk.private-fixture",
      "pk.invalid whitespace",
    ]) {
      const config = getMapProviderConfig({
        development: true,
        provider: "mapbox",
        mapboxToken: token,
      });
      expect(config.tileUrl).toBe("");
      expect(config.message).toBeTruthy();
      if (token) expect(config.message).not.toContain(token);
    }
  });

  it("fails closed for an unknown provider without echoing configuration", () => {
    const config = getMapProviderConfig({
      development: true,
      provider: "unknown-private-value",
    });
    expect(config.tileUrl).toBe("");
    expect(config.message).not.toContain("unknown-private-value");
  });
});
