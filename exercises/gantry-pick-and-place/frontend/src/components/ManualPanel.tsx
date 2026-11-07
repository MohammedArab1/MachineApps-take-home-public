import { useState } from "react";

import type { StatusSnapshot } from "../types";
import { cubeLocationLabel } from "../lib/format";

interface ManualPanelProps {
  status: StatusSnapshot;
  connected: boolean;
  pending: string | null;
  onJog: (axis: "x" | "y" | "z", delta: number) => void;
  onOpenGripper: () => void;
  onCloseGripper: () => void;
  onResetCube: () => void;
}

const JOG_STEPS = [10, 50, 100];
const AXES = ["x", "y", "z"] as const;

export function ManualPanel({
  status,
  connected,
  pending,
  onJog,
  onOpenGripper,
  onCloseGripper,
  onResetCube,
}: ManualPanelProps) {
  const [step, setStep] = useState(50);
  const busy = status.busy;
  const faulted = status.state === "fault";
  const locked = !connected || busy || faulted || pending !== null;
  const gripper = status.gripper;
  const cubeLocation = status.cubeLocation || "table_a";
  const cubeLabel = cubeLocationLabel(cubeLocation);

  let hint = "The robot is idle. Jogs use the configured speed.";
  if (faulted) hint = "Reset the fault before manual control.";
  else if (busy) hint = "The robot is moving. Stop it before manual control.";
  else if (!connected) hint = "Live connection lost. Manual control is disabled.";

  return (
    <section className="panel manual" aria-labelledby="manual-heading">
      <div className="panel-heading">
        <div>
          <h2 id="manual-heading">Manual control</h2>
          <p className="panel-subtitle">Only available when the robot is idle</p>
        </div>
        <span className={`manual-state ${locked ? "manual-state--locked" : ""}`}>
          {locked ? "Locked" : "Ready"}
        </span>
      </div>

      <div className="manual-toolbar">
        <label htmlFor="jog-step">Jog step</label>
        <select
          id="jog-step"
          value={step}
          onChange={(event) => setStep(Number(event.target.value))}
          disabled={locked}
        >
          {JOG_STEPS.map((value) => (
            <option key={value} value={value}>
              {value} mm
            </option>
          ))}
        </select>
      </div>

      <div className="jog-grid" role="group" aria-label="Manual jog controls">
        {AXES.map((axis) => (
          <div className="jog-row" key={axis}>
            <span className="jog-axis">{axis.toUpperCase()}</span>
            <button
              type="button"
              className="button button--ghost"
              onClick={() => onJog(axis, -step)}
              disabled={locked}
              aria-label={`Jog ${axis.toUpperCase()} negative`}
            >
              −
            </button>
            <button
              type="button"
              className="button button--ghost"
              onClick={() => onJog(axis, step)}
              disabled={locked}
              aria-label={`Jog ${axis.toUpperCase()} positive`}
            >
              +
            </button>
          </div>
        ))}
      </div>

      <div className="gripper-buttons">
        <button
          type="button"
          className="button button--home"
          onClick={onOpenGripper}
          disabled={locked || gripper === "open"}
        >
          Open gripper
        </button>
        <button
          type="button"
          className="button button--ghost"
          onClick={onCloseGripper}
          disabled={locked || gripper === "closed"}
        >
          Close gripper
        </button>
      </div>

      <div className="cube-control">
        <div>
          <span>Cube</span>
          <strong data-testid="manual-cube-location">{cubeLabel}</strong>
        </div>
        <button
          type="button"
          className="button button--ghost button--small"
          onClick={onResetCube}
          disabled={locked || cubeLocation === "table_a" || gripper === "closed"}
        >
          Return cube to Table A
        </button>
      </div>

      {gripper === "closed" && cubeLocation === "held" && (
        <p className="manual-warning">
          The cube is held. Moving may carry it.
        </p>
      )}

      <p className="control-hint" data-testid="manual-hint">
        {hint}
      </p>
    </section>
  );
}
