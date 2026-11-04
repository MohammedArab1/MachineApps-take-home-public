import type { Position } from "../types";

export const STATE_LABELS: Record<string, string> = {
  ready: "Ready",
  fault: "Fault",
  Homing_moveHome: "Homing",
  Manual_move: "Manual move",
  Cycle_moveToPick: "Moving to cube",
  Cycle_lowerToPick: "Lowering to cube",
  Cycle_closeGripper: "Closing gripper",
  Cycle_liftFromPick: "Lifting cube",
  Cycle_moveToPlace: "Moving to destination",
  Cycle_lowerToPlace: "Lowering to destination",
  Cycle_openGripper: "Opening gripper",
  Cycle_liftFromPlace: "Lifting from destination",
};

export type StateTone = "ready" | "active" | "fault" | "idle";

export function stateLabel(state: string): string {
  return STATE_LABELS[state] ?? state;
}

export function stateTone(
  state: string,
  busy: boolean,
  fault: string,
): StateTone {
  if (state === "fault" || fault) return "fault";
  if (busy) return "active";
  if (state === "ready") return "ready";
  return "idle";
}

export function formatNumber(value: number | undefined, digits = 1): string {
  if (value === undefined || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

export function positionText(position: Position | undefined): string {
  if (!position) return "—";
  return `X ${formatNumber(position.x)}  Y ${formatNumber(position.y)}  Z ${formatNumber(position.z)}`;
}

export function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso || "—";
  return date.toLocaleTimeString([], { hour12: false });
}

export function formatPercent(progress: number): string {
  const clamped = Math.max(
    0,
    Math.min(1, Number.isFinite(progress) ? progress : 0),
  );
  return `${Math.round(clamped * 100)}%`;
}

export type EventTone = "info" | "warning" | "error";

export function levelTone(level: string): EventTone {
  if (level === "error") return "error";
  if (level === "warning") return "warning";
  return "info";
}
