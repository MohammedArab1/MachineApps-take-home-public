import { describe, expect, it } from "vitest";

import {
  GRID_VALUES,
  SCENE_SIZE,
  TABLES,
  Z_GAUGE,
  clampWorld,
  rectToSvg,
  worldToSvg,
  zToGauge,
} from "./scene";

describe("worldToSvg", () => {
  it("maps the origin to the centre", () => {
    expect(worldToSvg(0, 0)).toEqual({ cx: 320, cy: 320 });
  });

  it("maps the workspace corners", () => {
    expect(worldToSvg(-1000, 1000)).toEqual({ cx: 44, cy: 44 });
    expect(worldToSvg(1000, -1000)).toEqual({ cx: 596, cy: 596 });
  });

  it("maps Y up to SVG Y down", () => {
    expect(worldToSvg(0, 500).cy).toBeLessThan(worldToSvg(0, -500).cy);
  });
});

describe("clampWorld", () => {
  it("clamps to the workspace and handles non-finite values", () => {
    expect(clampWorld(5000)).toBe(1000);
    expect(clampWorld(-5000)).toBe(-1000);
    expect(clampWorld(Number.NaN)).toBe(0);
  });
});

describe("tables", () => {
  it("maps Table A and Table B to their footprint regions", () => {
    expect(rectToSvg(TABLES.a)).toEqual({
      x: 44,
      y: 44,
      width: 138,
      height: 138,
    });
    const tableB = rectToSvg(TABLES.b);
    expect(tableB.x).toBeCloseTo(458);
    expect(tableB.y).toBeCloseTo(458);
    expect(tableB.width).toBe(138);
    expect(tableB.height).toBe(138);
  });

  it("labels the tables", () => {
    expect(TABLES.a.label).toBe("Table A");
    expect(TABLES.b.label).toBe("Table B");
  });
});

describe("Z gauge", () => {
  it("maps Z to the gauge and clamps", () => {
    expect(zToGauge(0)).toBe(Z_GAUGE.bottom);
    expect(zToGauge(1000)).toBe(Z_GAUGE.top);
    expect(zToGauge(500)).toBe((Z_GAUGE.top + Z_GAUGE.bottom) / 2);
    expect(zToGauge(-100)).toBe(Z_GAUGE.bottom);
    expect(zToGauge(2000)).toBe(Z_GAUGE.top);
    expect(zToGauge(Number.NaN)).toBe(Z_GAUGE.bottom);
  });
});

describe("scene constants", () => {
  it("includes the origin in the grid", () => {
    expect(GRID_VALUES).toContain(0);
    expect(SCENE_SIZE).toBe(640);
  });
});
