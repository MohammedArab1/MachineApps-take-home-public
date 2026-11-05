import { create } from "@bufbuild/protobuf";
import { createClient } from "@connectrpc/connect";
import { createConnectTransport } from "@connectrpc/connect-web";

import {
  GantryPickAndPlaceService,
  JogRobotRequestSchema,
  SetConfigRequestSchema,
} from "./gen/app_pb";
import type { ConfigPayload } from "./types";

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "/rpc";

export const client = createClient(
  GantryPickAndPlaceService,
  createConnectTransport({ baseUrl, useBinaryFormat: false }),
);

const QUERY_TIMEOUT_MS = 5_000;
const COMMAND_TIMEOUT_MS = 10_000;

export const openStatus = (signal: AbortSignal) =>
  client.status({}, { signal });

export const openEvents = (signal: AbortSignal) =>
  client.events({}, { signal });

export const getStatus = () =>
  client.getStatus({}, { timeoutMs: QUERY_TIMEOUT_MS });

export const getConfig = () =>
  client.getConfig({}, { timeoutMs: QUERY_TIMEOUT_MS });

export const getRobotPosition = () =>
  client.getRobotPosition({}, { timeoutMs: QUERY_TIMEOUT_MS });

export const setConfig = (config: ConfigPayload) =>
  client.setConfig(create(SetConfigRequestSchema, config), {
    timeoutMs: COMMAND_TIMEOUT_MS,
  });

export const jogRobot = (axis: string, delta: number) =>
  client.jogRobot(create(JogRobotRequestSchema, { axis, delta }), {
    timeoutMs: COMMAND_TIMEOUT_MS,
  });

export const openGripper = () =>
  client.openGripper({}, { timeoutMs: COMMAND_TIMEOUT_MS });

export const closeGripper = () =>
  client.closeGripper({}, { timeoutMs: COMMAND_TIMEOUT_MS });

export const homeRobot = () =>
  client.homeRobot({}, { timeoutMs: COMMAND_TIMEOUT_MS });

export const startSequence = () =>
  client.startSequence({}, { timeoutMs: COMMAND_TIMEOUT_MS });

export const stopSequence = () =>
  client.stopSequence({}, { timeoutMs: COMMAND_TIMEOUT_MS });

export const resetRobot = () =>
  client.reset({}, { timeoutMs: COMMAND_TIMEOUT_MS });

export const simulateFault = () =>
  client.simulateFault({}, { timeoutMs: COMMAND_TIMEOUT_MS });

export const recentEvents = () =>
  client.recentEvents({}, { timeoutMs: QUERY_TIMEOUT_MS });
