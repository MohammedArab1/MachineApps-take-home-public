import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TelemetryPanel } from "./TelemetryPanel";
import { configFixture, position, statusFixture } from "../test/fixtures";

describe("TelemetryPanel", () => {
  it("renders robot telemetry, state, progress, and configuration", () => {
    render(
      <TelemetryPanel
        status={statusFixture({
          robotPosition: position(10, 20, 30),
          gripper: "closed",
          moving: true,
          busy: true,
          state: "Cycle_lowerToPick",
          step: "Lowering to cube",
          progress: 0.5,
          config: configFixture(),
        })}
      />,
    );

    expect(screen.getByTestId("telemetry-x")).toHaveTextContent("10.0");
    expect(screen.getByTestId("telemetry-y")).toHaveTextContent("20.0");
    expect(screen.getByTestId("telemetry-z")).toHaveTextContent("30.0");
    expect(screen.getByTestId("telemetry-gripper")).toHaveTextContent("Closed");
    expect(screen.getByTestId("telemetry-motion")).toHaveTextContent("Moving");
    expect(screen.getByTestId("telemetry-state")).toHaveTextContent(
      "Cycle_lowerToPick",
    );
    expect(screen.getByTestId("telemetry-step")).toHaveTextContent(
      "Lowering to cube",
    );
    expect(screen.getByTestId("telemetry-cube-location")).toHaveTextContent(
      "On Table A",
    );
    expect(screen.getByTestId("telemetry-state-pill")).toHaveTextContent(
      "Lowering to cube",
    );
    expect(screen.getByTestId("telemetry-progress-label")).toHaveTextContent(
      "50%",
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "50",
    );
    expect(screen.getByTestId("telemetry-cube")).toHaveTextContent("X -650.0");
    expect(screen.getByTestId("telemetry-destination")).toHaveTextContent(
      "X 630.0",
    );
    expect(screen.getByTestId("telemetry-home")).toHaveTextContent("X 0.0");
  });

  it("shows the fault state", () => {
    render(
      <TelemetryPanel
        status={statusFixture({
          state: "fault",
          step: "Fault",
          fault: "simulated failure",
        })}
      />,
    );

    expect(screen.getByTestId("telemetry-state")).toHaveTextContent("fault");
    expect(screen.getByTestId("telemetry-state-pill")).toHaveTextContent(
      "Fault",
    );
  });

  it("handles missing robot and config data", () => {
    render(
      <TelemetryPanel
        status={statusFixture({ robotPosition: undefined, config: undefined })}
      />,
    );

    expect(screen.getByTestId("telemetry-x")).toHaveTextContent("0.0");
    expect(screen.getByTestId("telemetry-cube")).toHaveTextContent("—");
    expect(screen.getByTestId("telemetry-destination")).toHaveTextContent("—");
    expect(screen.getByTestId("telemetry-home")).toHaveTextContent("—");
  });
});
