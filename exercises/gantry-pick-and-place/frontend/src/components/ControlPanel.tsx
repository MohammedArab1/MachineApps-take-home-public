import type { StatusSnapshot } from "../types";

interface ControlPanelProps {
  status: StatusSnapshot;
  connected: boolean;
  pending: string | null;
  devTools: boolean;
  onHome: () => void;
  onStart: () => void;
  onStop: () => void;
  onReset: () => void;
  onSimulateFault: () => void;
}

function pendingLabel(pending: string | null, name: string, label: string): string {
  return pending === name ? `${label}…` : label;
}

export function ControlPanel({
  status,
  connected,
  pending,
  devTools,
  onHome,
  onStart,
  onStop,
  onReset,
  onSimulateFault,
}: ControlPanelProps) {
  const busy = status.busy;
  const faulted = status.state === "fault";
  const commandsBlocked = pending !== null;

  const startDisabled = !connected || busy || faulted || commandsBlocked;
  const homeDisabled = !connected || busy || faulted || commandsBlocked;
  const stopDisabled = !busy || commandsBlocked;
  const resetDisabled = !connected || !faulted || commandsBlocked;
  const faultDisabled = !devTools || faulted || commandsBlocked;

  let hint = "Ready for the next command.";
  if (faulted) hint = "The robot is faulted. Reset before moving.";
  else if (!connected) hint = "Live connection lost. Start and Home are disabled.";
  else if (busy) hint = "An operation is running. Stop is available.";

  return (
    <section className="panel controls" aria-labelledby="controls-heading">
      <div className="panel-heading">
        <div>
          <h2 id="controls-heading">Controls</h2>
          <p className="panel-subtitle">Commands run through the state machine</p>
        </div>
      </div>

      <div className="button-grid">
        <button
          type="button"
          className="button button--start"
          onClick={onStart}
          disabled={startDisabled}
          aria-busy={pending === "start"}
        >
          {pendingLabel(pending, "start", "Start sequence")}
        </button>
        <button
          type="button"
          className="button button--home"
          onClick={onHome}
          disabled={homeDisabled}
          aria-busy={pending === "home"}
        >
          {pendingLabel(pending, "home", "Home robot")}
        </button>
        <button
          type="button"
          className="button button--stop"
          onClick={onStop}
          disabled={stopDisabled}
          aria-busy={pending === "stop"}
        >
          {pendingLabel(pending, "stop", "Stop")}
        </button>
        <button
          type="button"
          className="button button--ghost"
          onClick={onReset}
          disabled={resetDisabled}
          aria-busy={pending === "reset"}
        >
          {pendingLabel(pending, "reset", "Reset fault")}
        </button>
      </div>

      <p className="control-hint" data-testid="control-hint">
        {hint}
      </p>

      {devTools && (
        <details className="dev-tools">
          <summary>Developer tools</summary>
          <p>
            Simulate a controller fault to inspect the error and recovery path.
          </p>
          <button
            type="button"
            className="button button--danger"
            onClick={onSimulateFault}
            disabled={faultDisabled}
            aria-busy={pending === "fault"}
          >
            {pendingLabel(pending, "fault", "Simulate fault")}
          </button>
        </details>
      )}
    </section>
  );
}
