import { create } from "@bufbuild/protobuf";

import {
  EventListSchema,
  EventSchema,
  MachineConfigSchema,
  StatusSnapshotSchema,
} from "../gen/app_pb";
import type {
  ActionResult,
  Event,
  EventList,
  MachineConfig,
  Position,
  StatusSnapshot,
} from "../types";

export function position(x = 0, y = 0, z = 0): Position {
  return { $typeName: "vention.app.v1.Position", x, y, z };
}

export function configFixture(
  overrides: Partial<MachineConfig> = {},
): MachineConfig {
  return {
    ...create(MachineConfigSchema, {
      cubePosition: { x: -750, y: 750, z: 0 },
      destinationPosition: { x: 700, y: -700, z: 0 },
      homePosition: { x: 0, y: 0, z: 0 },
      speed: 90,
      approachHeight: 100,
    }),
    ...overrides,
  };
}

export function statusFixture(
  overrides: Partial<StatusSnapshot> = {},
): StatusSnapshot {
  return {
    ...create(StatusSnapshotSchema, {
      robotPosition: { x: 0, y: 0, z: 0 },
      gripper: "open",
      moving: false,
      busy: false,
      state: "ready",
      step: "Ready",
      fault: "",
      progress: 0,
      config: configFixture(),
      limits: { x: 1000, y: 1000, z: 1000 },
      updatedAt: "2026-11-03T12:00:00+00:00",
    }),
    ...overrides,
  };
}

export function eventFixture(overrides: Partial<Event> = {}): Event {
  return {
    ...create(EventSchema, {
      id: 1,
      timestamp: "2026-11-03T12:00:00+00:00",
      level: "info",
      message: "Test event",
      detail: "",
    }),
    ...overrides,
  };
}

export function eventList(events: Event[]): EventList {
  return create(EventListSchema, { events });
}

export function actionResult(
  ok: boolean,
  message: string,
  status: StatusSnapshot = statusFixture(),
): ActionResult {
  return {
    $typeName: "vention.app.v1.ActionResult",
    ok,
    message,
    status,
  };
}
