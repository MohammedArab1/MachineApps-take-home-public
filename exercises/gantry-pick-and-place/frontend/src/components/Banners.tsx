import type { CommandMessage } from "../types";

interface FaultBannerProps {
  message: string;
  disabled: boolean;
  onReset: () => void;
}

export function FaultBanner({ message, disabled, onReset }: FaultBannerProps) {
  return (
    <div className="banner banner--fault" role="alert" data-testid="fault-banner">
      <div>
        <strong>Robot fault</strong>
        <p>{message || "The state machine is in a fault state."}</p>
      </div>
      <button
        type="button"
        className="button button--ghost"
        onClick={onReset}
        disabled={disabled}
      >
        Reset fault
      </button>
    </div>
  );
}

interface ConnectionBannerProps {
  connected: boolean;
}

export function ConnectionBanner({ connected }: ConnectionBannerProps) {
  if (connected) return null;
  return (
    <div
      className="banner banner--warning"
      role="status"
      data-testid="connection-banner"
    >
      <div>
        <strong>Live connection lost</strong>
        <p>
          Reconnecting automatically. The values below may be stale; Start and
          Home are disabled until the stream returns.
        </p>
      </div>
    </div>
  );
}

interface CommandAlertProps {
  message: CommandMessage;
  onDismiss: () => void;
}

export function CommandAlert({ message, onDismiss }: CommandAlertProps) {
  return (
    <div
      className={`banner banner--${message.ok ? "success" : "error"}`}
      role={message.ok ? "status" : "alert"}
      data-testid="command-alert"
    >
      <div>
        <strong>{message.ok ? "Command accepted" : "Command rejected"}</strong>
        <p>{message.message}</p>
      </div>
      <button
        type="button"
        className="button button--ghost button--small"
        onClick={onDismiss}
      >
        Dismiss
      </button>
    </div>
  );
}
