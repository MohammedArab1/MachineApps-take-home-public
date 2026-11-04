import { describe, expect, it } from "vitest";

import {
  GRID_VALUES,
  SCENE_SIZE,
  TABLE_A,
  TABLE_B,
  Z_GAUGE,
  clampWorld,
  diamondPoints,
  pointsAttribute,
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
  it("draws Table A as an inset 500 mm square", () => {
    const tableA = rectToSvg(TABLE_A);
    expect(tableA.x).toBeCloseTo(71.6);
    expect(tableA.y).toBeCloseTo(71.6);
    expect(tableA.width).toBe(138);
    expect(tableA.height).toBe(138);
    expect(TABLE_A.label).toBe("Table A");
  });

  it("draws Table B as a 500 mm square rotated 45 degrees", () => {
    const points = diamondPoints(TABLE_B);
    expect(points).toHaveLength(4);
    expect(points.map((point) => point.cx).sort((a, b) => a - b)[0]).toBeCloseTo(396.3);
    expect(points.map((point) => point.cx).sort((a, b) => a - b)[3]).toBeCloseTo(591.46);
    expect(points.map((point) => point.cy).sort((a, b) => a - b)[0]).toBeCloseTo(374.22);
    expect(points.map((point) => point.cy).sort((a, b) => a - b)[3]).toBeCloseTo(569.38);
    expect(pointsAttribute(points).split(" ")).toHaveLength(4);
    expect(TABLE_B.label).toBe("Table B");
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
