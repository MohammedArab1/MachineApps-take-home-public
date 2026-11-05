export type {
  ActionResult,
  Event,
  EventList,
  JogRobotRequest,
  MachineConfig,
  MoveRobotRequest,
  Position,
  RobotState,
  SetConfigRequest,
  StatusSnapshot,
} from "./gen/app_pb";

export interface AxisValues {
  x: string;
  y: string;
  z: string;
}

export interface ConfigValues {
  cube: AxisValues;
  destination: AxisValues;
  home: AxisValues;
  speed: string;
  approachHeight: string;
}

export interface ConfigPayload {
  cubePosition: { x: number; y: number; z: number };
  destinationPosition: { x: number; y: number; z: number };
  homePosition: { x: number; y: number; z: number };
  speed: number;
  approachHeight: number;
}

export interface CommandMessage {
  ok: boolean;
  message: string;
}
