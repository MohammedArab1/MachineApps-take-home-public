import type { StatusSnapshot } from "../types";
import { cubeLocationLabel } from "../lib/format";

interface CubePanelProps {
  status: StatusSnapshot;
  connected: boolean;
  pending: string | null;
  onResetCube: () => void;
}

export function CubePanel({
  status,
  connected,
  pending,
  onResetCube,
}: CubePanelProps) {
  const busy = status.busy;
  const faulted = status.state === "fault";
  const cubeLocation = status.cubeLocation || "table_a";
  const cubeLabel = cubeLocationLabel(cubeLocation);
  const resetDisabled =
    !connected ||
    busy ||
    faulted ||
    pending !== null ||
    cubeLocation === "table_a" ||
    status.gripper === "closed";

  let hint = "The cube is in its starting position on Table A.";
  if (faulted) hint = "Reset the fault before resetting the cube.";
  else if (!connected) hint = "Live connection lost. Cube reset is disabled.";
  else if (busy) hint = "The robot is moving. Stop the sequence before resetting the cube.";
  else if (cubeLocation === "held") {
    hint = "The cube is held. Resume the sequence to place it on Table B.";
  } else if (cubeLocation === "table_b") {
    hint = "The cube is on Table B. Return it to Table A for another run.";
  } else if (cubeLocation === "unknown") {
    hint = "The cube location is unknown. Return it to Table A.";
  }

  return (
    <section className="panel cube-panel" aria-labelledby="cube-heading">
      <div className="panel-heading">
        <div>
          <h2 id="cube-heading">Cube</h2>
          <p className="panel-subtitle">Simulation state</p>
        </div>
      </div>

      <div className="cube-state">
        <span>Location</span>
        <strong data-testid="cube-location">{cubeLabel}</strong>
      </div>

      <button
        type="button"
        className="button button--ghost"
        onClick={onResetCube}
        disabled={resetDisabled}
        aria-busy={pending === "reset-cube"}
      >
        {pending === "reset-cube"
          ? "Returning cube…"
          : "Return cube to Table A"}
      </button>

      <p className="control-hint" data-testid="cube-hint">
        {hint}
      </p>
    </section>
  );
}
