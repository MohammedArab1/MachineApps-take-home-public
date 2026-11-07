import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./app";
import * as client from "./client";
import type { Event, StatusSnapshot } from "./types";
import {
  actionResult,
  eventFixture,
  eventList,
  position,
  statusFixture,
} from "./test/fixtures";

vi.mock("./client", () => ({
  openStatus: vi.fn(),
  openEvents: vi.fn(),
  recentEvents: vi.fn(),
  setConfig: vi.fn(),
  jogRobot: vi.fn(),
  openGripper: vi.fn(),
  closeGripper: vi.fn(),
  resetCube: vi.fn(),
  homeRobot: vi.fn(),
  startSequence: vi.fn(),
  resumeSequence: vi.fn(),
  stopSequence: vi.fn(),
  resetRobot: vi.fn(),
  simulateFault: vi.fn(),
}));

function hangingStream<T>(first?: T) {
  return (signal: AbortSignal): AsyncIterable<T> =>
    (async function* () {
      if (first !== undefined) yield first;
      await new Promise<void>((_, reject) => {
        if (signal.aborted) {
          reject(new Error("aborted"));
          return;
        }
        signal.addEventListener(
          "abort",
          () => reject(new Error("aborted")),
          { once: true },
        );
      });
    })();
}

function failingStream<T>(first: T) {
  return (): AsyncIterable<T> =>
    (async function* () {
      yield first;
      throw new Error("dropped");
    })();
}

function mockStreams(status: StatusSnapshot, events: Event[] = []) {
  vi.mocked(client.openStatus).mockImplementation(hangingStream(status));
  vi.mocked(client.openEvents).mockImplementation((signal) => {
    const event = events[0];
    return hangingStream<Event>(event)(signal);
  });
  vi.mocked(client.recentEvents).mockResolvedValue(eventList([]));
}

beforeEach(() => {
  vi.mocked(client.recentEvents).mockResolvedValue(eventList([]));
  vi.mocked(client.setConfig).mockResolvedValue(
    actionResult(true, "Configuration saved"),
  );
  vi.mocked(client.jogRobot).mockResolvedValue(
    actionResult(true, "Manual jog started"),
  );
  vi.mocked(client.openGripper).mockResolvedValue(
    actionResult(true, "Gripper open"),
  );
  vi.mocked(client.closeGripper).mockResolvedValue(
    actionResult(true, "Gripper closed"),
  );
  vi.mocked(client.resetCube).mockResolvedValue(
    actionResult(true, "Cube returned to Table A"),
  );
  vi.mocked(client.homeRobot).mockResolvedValue(
    actionResult(true, "Homing started"),
  );
  vi.mocked(client.startSequence).mockResolvedValue(
    actionResult(true, "Sequence started"),
  );
  vi.mocked(client.resumeSequence).mockResolvedValue(
    actionResult(true, "Sequence resumed"),
  );
  vi.mocked(client.stopSequence).mockResolvedValue(
    actionResult(true, "Operation stopped"),
  );
  vi.mocked(client.resetRobot).mockResolvedValue(
    actionResult(true, "Fault cleared"),
  );
  vi.mocked(client.simulateFault).mockResolvedValue(
    actionResult(true, "Fault simulated"),
  );
});

describe("App", () => {
  it("shows a loading screen until the first status arrives", () => {
    vi.mocked(client.openStatus).mockImplementation(hangingStream());
    vi.mocked(client.openEvents).mockImplementation(hangingStream());

    render(<App />);

    expect(
      screen.getByText("Connecting to the robot controller…"),
    ).toBeInTheDocument();
    expect(screen.getByText("Pick & Place")).toBeInTheDocument();
  });

  it("renders the dashboard from the status stream", async () => {
    mockStreams(statusFixture());

    render(<App />);

    expect(await screen.findByText("Telemetry")).toBeInTheDocument();
    expect(screen.getByTestId("connection-state")).toHaveTextContent("Live");
    expect(screen.getByTestId("telemetry-state-pill")).toHaveTextContent(
      "Ready",
    );
    expect(screen.getByText("Controls")).toBeInTheDocument();
    expect(screen.getByText("Configuration")).toBeInTheDocument();
    expect(screen.getByText("Activity")).toBeInTheDocument();
    expect(screen.getByTestId("activity-empty")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start sequence" })).toBeEnabled();
  });

  it("resumes a stopped sequence with the cube in the gripper", async () => {
    const user = userEvent.setup();
    mockStreams(
      statusFixture({
        gripper: "closed",
        cubeLocation: "held",
        cubePosition: position(-650, 650, 0),
      }),
    );

    render(<App />);

    await user.click(
      await screen.findByRole("button", { name: "Resume sequence" }),
    );
    expect(client.resumeSequence).toHaveBeenCalledOnce();
    expect(client.startSequence).not.toHaveBeenCalled();
  });

  it("shows the fault banner and resets the fault", async () => {
    const user = userEvent.setup();
    mockStreams(
      statusFixture({ state: "fault", step: "Fault", fault: "gripper stuck" }),
    );

    render(<App />);

    const banner = await screen.findByTestId("fault-banner");
    expect(banner).toHaveTextContent("gripper stuck");
    await user.click(within(banner).getByRole("button", { name: "Reset fault" }));

    expect(client.resetRobot).toHaveBeenCalledOnce();
    expect(await screen.findByTestId("command-alert")).toHaveTextContent(
      "Fault cleared",
    );
  });

  it("starts the sequence and shows the command result", async () => {
    const user = userEvent.setup();
    mockStreams(statusFixture());

    render(<App />);
    await screen.findByText("Telemetry");

    await user.click(screen.getByRole("button", { name: "Start sequence" }));

    expect(client.startSequence).toHaveBeenCalledOnce();
    expect(await screen.findByTestId("command-alert")).toHaveTextContent(
      "Sequence started",
    );
  });

  it("stops a running sequence", async () => {
    const user = userEvent.setup();
    mockStreams(
      statusFixture({
        busy: true,
        state: "Cycle_moveToPick",
        step: "Moving to cube",
      }),
    );

    render(<App />);
    await screen.findByText("Telemetry");

    await user.click(screen.getByRole("button", { name: "Stop" }));

    expect(client.stopSequence).toHaveBeenCalledOnce();
  });

  it("simulates a fault from the developer tools", async () => {
    const user = userEvent.setup();
    mockStreams(statusFixture());

    render(<App />);
    await screen.findByText("Telemetry");

    await user.click(screen.getByText("Developer tools"));
    await user.click(screen.getByRole("button", { name: "Simulate fault" }));

    expect(client.simulateFault).toHaveBeenCalledOnce();
  });

  it("saves the configuration", async () => {
    const user = userEvent.setup();
    mockStreams(statusFixture());

    render(<App />);
    await screen.findByText("Telemetry");

    const cubeX = screen.getByLabelText("Cube X");
    await user.clear(cubeX);
    await user.type(cubeX, "-500");
    await user.click(
      screen.getByRole("button", { name: "Save configuration" }),
    );

    expect(client.setConfig).toHaveBeenCalledWith({
      cubePosition: { x: -500, y: 650, z: 0 },
      destinationPosition: { x: 630, y: -550, z: 0 },
      homePosition: { x: 0, y: 0, z: 0 },
      speed: 90,
      approachHeight: 100,
    });
    expect(await screen.findByTestId("config-message")).toHaveTextContent(
      "Configuration saved",
    );
  });

  it("merges live and recent events", async () => {
    vi.mocked(client.openStatus).mockImplementation(
      hangingStream(statusFixture()),
    );
    vi.mocked(client.openEvents).mockImplementation((signal) =>
      hangingStream<Event>(
        eventFixture({ id: 2, message: "Live event" }),
      )(signal),
    );
    vi.mocked(client.recentEvents).mockResolvedValue(
      eventList([eventFixture({ id: 1, message: "Recent event" })]),
    );

    render(<App />);

    expect(await screen.findByText("Live event")).toBeInTheDocument();
    expect(await screen.findByText("Recent event")).toBeInTheDocument();
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Live event");
    expect(items[1]).toHaveTextContent("Recent event");
  });

  it("shows the connection banner when the status stream drops", async () => {
    vi.mocked(client.openStatus).mockImplementation(failingStream(statusFixture()));
    vi.mocked(client.openEvents).mockImplementation(hangingStream());

    render(<App />);

    expect(
      await screen.findByTestId("connection-banner"),
    ).toHaveTextContent("Live connection lost");
    expect(screen.getByRole("button", { name: "Start sequence" })).toBeDisabled();
  });

  it("survives a recent-events request failure", async () => {
    mockStreams(statusFixture());
    vi.mocked(client.recentEvents).mockRejectedValue(new Error("offline"));

    render(<App />);

    expect(await screen.findByText("Telemetry")).toBeInTheDocument();
    expect(screen.getByTestId("activity-empty")).toBeInTheDocument();
  });

  it("dismisses a command alert", async () => {
    const user = userEvent.setup();
    mockStreams(statusFixture());

    render(<App />);
    await screen.findByText("Telemetry");
    await user.click(screen.getByRole("button", { name: "Start sequence" }));
    const alert = await screen.findByTestId("command-alert");
    await user.click(within(alert).getByRole("button", { name: "Dismiss" }));

    await waitFor(() =>
      expect(screen.queryByTestId("command-alert")).not.toBeInTheDocument(),
    );
  });

  it("jogs and controls the gripper from the manual panel", async () => {
    const user = userEvent.setup();
    mockStreams(statusFixture());

    render(<App />);
    await screen.findByText("Telemetry");

    await user.click(screen.getByRole("button", { name: "Jog X positive" }));
    expect(client.jogRobot).toHaveBeenCalledWith("x", 50);

    await user.click(screen.getByRole("button", { name: "Close gripper" }));
    expect(client.closeGripper).toHaveBeenCalledOnce();
  });
});
