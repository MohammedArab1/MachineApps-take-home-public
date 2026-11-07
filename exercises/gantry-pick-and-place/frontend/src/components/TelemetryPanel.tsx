import type { StatusSnapshot } from "../types";
import {
  formatNumber,
  cubeLocationLabel,
  formatPercent,
  positionText,
  stateLabel,
  stateTone,
} from "../lib/format";

interface TelemetryPanelProps {
  status: StatusSnapshot;
}

const DEFAULT_POSITION = { x: 0, y: 0, z: 0 };

export function TelemetryPanel({ status }: TelemetryPanelProps) {
  const robot = status.robotPosition ?? DEFAULT_POSITION;
  const config = status.config;
  const tone = stateTone(status.state, status.busy, status.fault);
  const progress = Math.max(0, Math.min(1, status.progress || 0));
  const gripper = status.gripper === "closed" ? "Closed" : "Open";

  return (
    <section className="panel telemetry" aria-labelledby="telemetry-heading">
      <div className="panel-heading">
        <div>
          <h2 id="telemetry-heading">Telemetry</h2>
          <p className="panel-subtitle">Live from the state machine</p>
        </div>
        <span className={`state-pill state-pill--${tone}`} data-testid="telemetry-state-pill">
          {status.step || stateLabel(status.state)}
        </span>
      </div>

      <div className="telemetry-axes">
        {(["x", "y", "z"] as const).map((axis) => (
          <div className="axis-metric" key={axis}>
            <span>{axis.toUpperCase()}</span>
            <strong data-testid={`telemetry-${axis}`}>
              {formatNumber(robot[axis])}
            </strong>
            <small>mm</small>
          </div>
        ))}
      </div>

      <div className="telemetry-rows">
        <div className="telemetry-row">
          <span>Gripper</span>
          <strong data-testid="telemetry-gripper">{gripper}</strong>
        </div>
        <div className="telemetry-row">
          <span>Motion</span>
          <strong data-testid="telemetry-motion">
            {status.moving ? "Moving" : "Idle"}
          </strong>
        </div>
        <div className="telemetry-row">
          <span>State machine</span>
          <code data-testid="telemetry-state">{status.state}</code>
        </div>
        <div className="telemetry-row">
          <span>Step</span>
          <strong data-testid="telemetry-step">{status.step}</strong>
        </div>
        <div className="telemetry-row">
          <span>Cube</span>
          <strong data-testid="telemetry-cube-location">
            {cubeLocationLabel(status.cubeLocation)}
          </strong>
        </div>
      </div>

      <div className="progress-block">
        <div className="progress-label">
          <span>Cycle progress</span>
          <strong data-testid="telemetry-progress-label">
            {formatPercent(progress)}
          </strong>
        </div>
        <div
          className="progress-track"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(progress * 100)}
          aria-label="Cycle progress"
        >
          <div className="progress-fill" style={{ width: `${progress * 100}%` }} />
        </div>
      </div>

      <div className="config-summary">
        <div>
          <span>Cube start</span>
          <code data-testid="telemetry-cube">{positionText(config?.cubePosition)}</code>
        </div>
        <div>
          <span>Destination</span>
          <code data-testid="telemetry-destination">
            {positionText(config?.destinationPosition)}
          </code>
        </div>
        <div>
          <span>Home</span>
          <code data-testid="telemetry-home">{positionText(config?.homePosition)}</code>
        </div>
      </div>
    </section>
  );
}
