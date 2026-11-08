import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CubePanel } from "./CubePanel";
import { position, statusFixture } from "../test/fixtures";

function renderPanel(
  status = statusFixture(),
  overrides: Partial<Parameters<typeof CubePanel>[0]> = {},
) {
  const props = {
    status,
    connected: true,
    pending: null,
    onResetCube: vi.fn(),
    ...overrides,
  };
  const result = render(<CubePanel {...props} />);
  return { ...result, props };
}

describe("CubePanel", () => {
  it("shows the cube on Table A and disables reset", () => {
    renderPanel();

    expect(screen.getByTestId("cube-location")).toHaveTextContent("On Table A");
    expect(
      screen.getByRole("button", { name: "Return cube to Table A" }),
    ).toBeDisabled();
    expect(screen.getByTestId("cube-hint")).toHaveTextContent(
      "starting position on Table A",
    );
  });

  it("returns the cube to Table A from Table B", async () => {
    const user = userEvent.setup();
    const panel = renderPanel(
      statusFixture({
        cubeLocation: "table_b",
        cubePosition: position(630, -550, 0),
      }),
    );

    expect(screen.getByTestId("cube-location")).toHaveTextContent("On Table B");
    const reset = screen.getByRole("button", {
      name: "Return cube to Table A",
    });
    expect(reset).toBeEnabled();
    await user.click(reset);
    expect(panel.props.onResetCube).toHaveBeenCalledOnce();
  });

  it("explains that a held cube must be resumed", () => {
    renderPanel(
      statusFixture({
        gripper: "closed",
        cubeLocation: "held",
        cubePosition: position(-650, 650, 0),
      }),
    );

    expect(screen.getByTestId("cube-location")).toHaveTextContent(
      "In gripper",
    );
    expect(
      screen.getByRole("button", { name: "Return cube to Table A" }),
    ).toBeDisabled();
    expect(screen.getByTestId("cube-hint")).toHaveTextContent(
      "Resume the sequence to place it",
    );
  });

  it("locks reset while busy", () => {
    renderPanel(
      statusFixture({
        busy: true,
        state: "Cycle_moveToPick",
        step: "Moving to cube",
      }),
    );

    expect(
      screen.getByRole("button", { name: "Return cube to Table A" }),
    ).toBeDisabled();
    expect(screen.getByTestId("cube-hint")).toHaveTextContent(
      "Stop the sequence",
    );
  });

  it("locks reset in a fault, while disconnected, and while pending", () => {
    const faulted = renderPanel(
      statusFixture({ state: "fault", step: "Fault", fault: "boom" }),
    );
    expect(
      screen.getByRole("button", { name: "Return cube to Table A" }),
    ).toBeDisabled();
    expect(screen.getByTestId("cube-hint")).toHaveTextContent(
      "Reset the fault",
    );
    faulted.unmount();

    const offline = renderPanel(statusFixture(), { connected: false });
    expect(
      screen.getByRole("button", { name: "Return cube to Table A" }),
    ).toBeDisabled();
    expect(screen.getByTestId("cube-hint")).toHaveTextContent(
      "Live connection lost",
    );
    offline.unmount();

    renderPanel(
      statusFixture({
        cubeLocation: "table_b",
        cubePosition: position(630, -550, 0),
      }),
      { pending: "reset-cube" },
    );
    expect(
      screen.getByRole("button", { name: "Returning cube…" }),
    ).toBeDisabled();
  });
});
