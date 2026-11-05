import { useState } from "react";

import type { StatusSnapshot } from "../types";

interface ManualPanelProps {
  status: StatusSnapshot;
  connected: boolean;
  pending: string | null;
  onJog: (axis: "x" | "y" | "z", delta: number) => void;
  onOpenGripper: () => void;
  onCloseGripper: () => void;
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
}: ManualPanelProps) {
  const [step, setStep] = useState(50);
  const busy = status.busy;
  const faulted = status.state === "fault";
  const locked = !connected || busy || faulted || pending !== null;
  const gripper = status.gripper;

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

      {gripper === "closed" && (
        <p className="manual-warning">
          The gripper is closed. Moving may carry the cube.
        </p>
      )}

      <p className="control-hint" data-testid="manual-hint">
        {hint}
      </p>
    </section>
  );
}
