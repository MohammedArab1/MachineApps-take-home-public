export const SCENE_SIZE = 640;
export const SCENE_VIEW_WIDTH = SCENE_SIZE + 40;
export const SCENE_PAD = 44;
export const WORLD_LIMIT = 1000;
export const SCENE_SCALE = (SCENE_SIZE - 2 * SCENE_PAD) / (2 * WORLD_LIMIT);

export interface SvgPoint {
  cx: number;
  cy: number;
}

export interface WorldRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface TableRect extends WorldRect {
  label: string;
}

export interface RotatedTable {
  centerX: number;
  centerY: number;
  side: number;
  rotationDeg: number;
  label: string;
}

/**
 * Figure-faithful table geometry, in millimetres.
 *
 * Table A is a 500 mm square inset ~100 mm from the top and left cell edges.
 * Table B is a 500 mm square rotated 45 degrees; its right corner sits close
 * to the right cell edge and its bottom corner is inset ~100 mm.
 */
export const TABLE_A: TableRect = {
  x: -900,
  y: 400,
  width: 500,
  height: 500,
  label: "Table A",
};

export const TABLE_B: RotatedTable = {
  centerX: 630,
  centerY: -550,
  side: 500,
  rotationDeg: 45,
  label: "Table B",
};

export const GRID_VALUES = [
  -1000, -750, -500, -250, 0, 250, 500, 750, 1000,
];

export function clampWorld(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(-WORLD_LIMIT, Math.min(WORLD_LIMIT, value));
}

/** World coordinates use +Y up; SVG uses +Y down. */
export function worldToSvg(x: number, y: number): SvgPoint {
  return {
    cx: SCENE_PAD + (x + WORLD_LIMIT) * SCENE_SCALE,
    cy: SCENE_PAD + (WORLD_LIMIT - y) * SCENE_SCALE,
  };
}

export function rectToSvg(rect: WorldRect): {
  x: number;
  y: number;
  width: number;
  height: number;
} {
  const topLeft = worldToSvg(rect.x, rect.y + rect.height);
  return {
    x: topLeft.cx,
    y: topLeft.cy,
    width: rect.width * SCENE_SCALE,
    height: rect.height * SCENE_SCALE,
  };
}

/** Corners of a rotated square, converted to SVG coordinates. */
export function diamondPoints(table: RotatedTable): SvgPoint[] {
  const half = table.side / 2;
  const angle = (table.rotationDeg * Math.PI) / 180;
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  const corners = [
    { x: -half, y: -half },
    { x: half, y: -half },
    { x: half, y: half },
    { x: -half, y: half },
  ];
  return corners.map((corner) => {
    const rotatedX = corner.x * cos - corner.y * sin;
    const rotatedY = corner.x * sin + corner.y * cos;
    return worldToSvg(
      table.centerX + rotatedX,
      table.centerY + rotatedY,
    );
  });
}

export function pointsAttribute(points: SvgPoint[]): string {
  return points.map((point) => `${point.cx},${point.cy}`).join(" ");
}

export const Z_GAUGE = {
  x: 616,
  top: 80,
  bottom: 560,
};

/** Map a Z coordinate (0..1000) to the vertical gauge; clamp for display. */
export function zToGauge(z: number): number {
  const clamped = Math.max(0, Math.min(WORLD_LIMIT, Number.isFinite(z) ? z : 0));
  return (
    Z_GAUGE.bottom -
    (clamped / WORLD_LIMIT) * (Z_GAUGE.bottom - Z_GAUGE.top)
  );
}
