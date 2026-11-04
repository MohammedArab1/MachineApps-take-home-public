import type { StatusSnapshot } from "../types";
import { formatNumber } from "../lib/format";
import {
  GRID_VALUES,
  SCENE_PAD,
  SCENE_SIZE,
  SCENE_VIEW_WIDTH,
  TABLE_A,
  TABLE_B,
  Z_GAUGE,
  clampWorld,
  diamondPoints,
  pointsAttribute,
  rectToSvg,
  worldToSvg,
  zToGauge,
} from "../lib/scene";

interface SceneViewProps {
  status: StatusSnapshot;
}

const DEFAULT_POSITION = { x: 0, y: 0, z: 0 };

export function SceneView({ status }: SceneViewProps) {
  const robot = status.robotPosition ?? DEFAULT_POSITION;
  const cube = status.config?.cubePosition ?? DEFAULT_POSITION;
  const destination = status.config?.destinationPosition ?? DEFAULT_POSITION;
  const approach = status.config?.approachHeight ?? 0;

  const robotPoint = worldToSvg(clampWorld(robot.x), clampWorld(robot.y));
  const cubePoint = worldToSvg(clampWorld(cube.x), clampWorld(cube.y));
  const destinationPoint = worldToSvg(
    clampWorld(destination.x),
    clampWorld(destination.y),
  );
  const basePoint = worldToSvg(0, 0);
  const footprint = rectToSvg({ x: -1000, y: -1000, width: 2000, height: 2000 });
  const tableA = rectToSvg(TABLE_A);
  const tableBPoints = pointsAttribute(diamondPoints(TABLE_B));
  const tableALabel = worldToSvg(TABLE_A.x, TABLE_A.y + TABLE_A.height);
  const tableBLabel = worldToSvg(TABLE_B.centerX, TABLE_B.centerY + 250);
  const zMarker = zToGauge(robot.z);
  const approachMarker = zToGauge(approach);
  const isFault = status.state === "fault" || Boolean(status.fault);

  return (
    <section className="panel scene-panel" aria-labelledby="scene-heading">
      <div className="panel-heading">
        <div>
          <h2 id="scene-heading">Cell view</h2>
          <p className="panel-subtitle">2 m × 2 m footprint · millimetres</p>
        </div>
        <span className={`scene-legend ${isFault ? "scene-legend--fault" : ""}`}>
          {isFault ? "Fault" : status.moving ? "In motion" : "Idle"}
        </span>
      </div>

      <svg
        className={`scene ${isFault ? "scene--fault" : ""}`}
        viewBox={`0 0 ${SCENE_VIEW_WIDTH} ${SCENE_SIZE}`}
        role="img"
        aria-label={`Top-down cell view. Robot at X ${formatNumber(robot.x)}, Y ${formatNumber(robot.y)}, Z ${formatNumber(robot.z)}. Cube at X ${formatNumber(cube.x)}, Y ${formatNumber(cube.y)}, Z ${formatNumber(cube.z)}. Destination at X ${formatNumber(destination.x)}, Y ${formatNumber(destination.y)}, Z ${formatNumber(destination.z)}.`}
      >
        <rect
          className="scene-bg"
          x={0}
          y={0}
          width={SCENE_VIEW_WIDTH}
          height={SCENE_SIZE}
          rx={18}
        />

        {GRID_VALUES.map((value) => {
          const vertical = worldToSvg(value, 0);
          const horizontal = worldToSvg(0, value);
          const isAxis = value === 0;
          return (
            <g key={value}>
              <line
                className={isAxis ? "scene-grid scene-grid--axis" : "scene-grid"}
                x1={vertical.cx}
                y1={SCENE_PAD}
                x2={vertical.cx}
                y2={SCENE_SIZE - SCENE_PAD}
              />
              <line
                className={isAxis ? "scene-grid scene-grid--axis" : "scene-grid"}
                x1={SCENE_PAD}
                y1={horizontal.cy}
                x2={SCENE_SIZE - SCENE_PAD}
                y2={horizontal.cy}
              />
            </g>
          );
        })}

        <rect
          className="scene-footprint"
          x={footprint.x}
          y={footprint.y}
          width={footprint.width}
          height={footprint.height}
          rx={4}
        />

        <rect
          className="scene-table scene-table--a"
          data-testid="scene-table-a"
          x={tableA.x}
          y={tableA.y}
          width={tableA.width}
          height={tableA.height}
          rx={3}
        />
        <text
          className="scene-label scene-label--table"
          x={tableALabel.cx + 12}
          y={tableALabel.cy + 22}
          textAnchor="start"
        >
          {TABLE_A.label}
        </text>

        <polygon
          className="scene-table scene-table--b"
          data-testid="scene-table-b"
          points={tableBPoints}
        />
        <text
          className="scene-label scene-label--table"
          x={tableBLabel.cx}
          y={tableBLabel.cy}
          textAnchor="middle"
          dominantBaseline="middle"
          transform={`rotate(-45 ${tableBLabel.cx} ${tableBLabel.cy})`}
        >
          {TABLE_B.label}
        </text>

        <line
          className="scene-path"
          x1={basePoint.cx}
          y1={basePoint.cy}
          x2={cubePoint.cx}
          y2={cubePoint.cy}
        />
        <line
          className="scene-path scene-path--destination"
          x1={basePoint.cx}
          y1={basePoint.cy}
          x2={destinationPoint.cx}
          y2={destinationPoint.cy}
        />

        <circle
          className="scene-base"
          cx={basePoint.cx}
          cy={basePoint.cy}
          r={22}
        />
        <text
          className="scene-label"
          x={basePoint.cx}
          y={basePoint.cy + 36}
          textAnchor="middle"
        >
          Robot base
        </text>

        <circle
          className="scene-robot-halo"
          cx={robotPoint.cx}
          cy={robotPoint.cy}
          r={18}
        />
        <circle
          className="scene-robot"
          data-testid="scene-robot"
          cx={robotPoint.cx}
          cy={robotPoint.cy}
          r={9}
        />
        <line
          className="scene-robot-cross"
          x1={robotPoint.cx - 14}
          y1={robotPoint.cy}
          x2={robotPoint.cx + 14}
          y2={robotPoint.cy}
        />
        <line
          className="scene-robot-cross"
          x1={robotPoint.cx}
          y1={robotPoint.cy - 14}
          x2={robotPoint.cx}
          y2={robotPoint.cy + 14}
        />

        <rect
          className="scene-cube"
          data-testid="scene-cube"
          x={cubePoint.cx - 8}
          y={cubePoint.cy - 8}
          width={16}
          height={16}
          rx={3}
        />
        <text
          className="scene-label scene-label--marker"
          x={cubePoint.cx}
          y={cubePoint.cy - 15}
          textAnchor="middle"
        >
          Cube
        </text>

        <circle
          className="scene-destination"
          data-testid="scene-destination"
          cx={destinationPoint.cx}
          cy={destinationPoint.cy}
          r={12}
        />
        <line
          className="scene-destination-cross"
          x1={destinationPoint.cx - 7}
          y1={destinationPoint.cy}
          x2={destinationPoint.cx + 7}
          y2={destinationPoint.cy}
        />
        <line
          className="scene-destination-cross"
          x1={destinationPoint.cx}
          y1={destinationPoint.cy - 7}
          x2={destinationPoint.cx}
          y2={destinationPoint.cy + 7}
        />
        <text
          className="scene-label scene-label--marker"
          x={destinationPoint.cx}
          y={destinationPoint.cy + 27}
          textAnchor="middle"
        >
          Destination
        </text>

        <g className="scene-z-gauge" data-testid="scene-z-gauge">
          <text className="scene-label" x={Z_GAUGE.x} y={Z_GAUGE.top - 18} textAnchor="middle">
            Z
          </text>
          <line
            className="scene-z-track"
            x1={Z_GAUGE.x}
            y1={Z_GAUGE.top}
            x2={Z_GAUGE.x}
            y2={Z_GAUGE.bottom}
          />
          {[0, 250, 500, 750, 1000].map((value) => {
            const y = zToGauge(value);
            return (
              <g key={value}>
                <line
                  className="scene-z-tick"
                  x1={Z_GAUGE.x - 6}
                  y1={y}
                  x2={Z_GAUGE.x + 6}
                  y2={y}
                />
                <text
                  className="scene-z-label"
                  x={Z_GAUGE.x - 10}
                  y={y + 3}
                  textAnchor="end"
                >
                  {value}
                </text>
              </g>
            );
          })}
          <line
            className="scene-z-approach"
            x1={Z_GAUGE.x - 10}
            y1={approachMarker}
            x2={Z_GAUGE.x + 10}
            y2={approachMarker}
          />
          <circle
            className="scene-z-marker"
            data-testid="scene-z-marker"
            cx={Z_GAUGE.x}
            cy={zMarker}
            r={6}
          />
          <text
            className="scene-z-label scene-z-label--current"
            x={Z_GAUGE.x + 10}
            y={zMarker + 3}
          >
            {formatNumber(robot.z)}
          </text>
        </g>

        <text className="scene-axis-label" x={SCENE_SIZE - SCENE_PAD} y={SCENE_SIZE - 16} textAnchor="end">
          +X
        </text>
        <text className="scene-axis-label" x={SCENE_PAD} y={SCENE_PAD - 16}>
          +Y
        </text>
      </svg>
    </section>
  );
}
