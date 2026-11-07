import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ManualPanel } from "./ManualPanel";
import { position, statusFixture } from "../test/fixtures";

function renderPanel(
  status = statusFixture(),
  overrides: Partial<Parameters<typeof ManualPanel>[0]> = {},
) {
  const props = {
    status,
    connected: true,
    pending: null,
    onJog: vi.fn(),
    onOpenGripper: vi.fn(),
    onCloseGripper: vi.fn(),
    onResetCube: vi.fn(),
    ...overrides,
  };
  const result = render(<ManualPanel {...props} />);
  return { ...result, props };
}

describe("ManualPanel", () => {
  it("is enabled when the robot is idle", () => {
    renderPanel();

    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByLabelText("Jog step")).toBeEnabled();
    expect(screen.getByRole("button", { name: "Jog X positive" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Jog X negative" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Close gripper" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Open gripper" })).toBeDisabled();
  });

  it("jogs with the selected step and direction", async () => {
    const user = userEvent.setup();
    const panel = renderPanel();

    await user.click(screen.getByRole("button", { name: "Jog X positive" }));
    expect(panel.props.onJog).toHaveBeenLastCalledWith("x", 50);

    await user.selectOptions(screen.getByLabelText("Jog step"), "10");
    await user.click(screen.getByRole("button", { name: "Jog Y negative" }));
    expect(panel.props.onJog).toHaveBeenLastCalledWith("y", -10);

    await user.click(screen.getByRole("button", { name: "Jog Z positive" }));
    expect(panel.props.onJog).toHaveBeenLastCalledWith("z", 10);
  });

  it("opens and closes the gripper", async () => {
    const user = userEvent.setup();
    const panel = renderPanel();

    await user.click(screen.getByRole("button", { name: "Close gripper" }));
    expect(panel.props.onCloseGripper).toHaveBeenCalledOnce();

    panel.unmount();
    const closed = renderPanel(
      statusFixture({
        gripper: "closed",
        cubeLocation: "held",
        cubePosition: position(0, 0, 0),
      }),
    );
    expect(screen.getByRole("button", { name: "Open gripper" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Close gripper" })).toBeDisabled();
    expect(screen.getByText(/Moving may carry it/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open gripper" }));
    expect(closed.props.onOpenGripper).toHaveBeenCalledOnce();
  });

  it("shows the cube state and resets it to Table A", async () => {
    const user = userEvent.setup();
    const panel = renderPanel(
      statusFixture({ cubeLocation: "table_b", cubePosition: position(630, -550, 0) }),
    );

    expect(screen.getByTestId("manual-cube-location")).toHaveTextContent(
      "On Table B",
    );
    const reset = screen.getByRole("button", {
      name: "Return cube to Table A",
    });
    expect(reset).toBeEnabled();
    await user.click(reset);
    expect(panel.props.onResetCube).toHaveBeenCalledOnce();
  });

  it("disables cube reset when the cube is already at Table A", () => {
    renderPanel();
    expect(
      screen.getByRole("button", { name: "Return cube to Table A" }),
    ).toBeDisabled();
    expect(screen.getByTestId("manual-cube-location")).toHaveTextContent(
      "On Table A",
    );
  });

  it("locks while the robot is moving", () => {
    renderPanel(
      statusFixture({ busy: true, state: "Cycle_moveToPick", step: "Moving to cube" }),
    );

    expect(screen.getByText("Locked")).toBeInTheDocument();
    expect(screen.getByLabelText("Jog step")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Jog X positive" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Open gripper" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Close gripper" })).toBeDisabled();
    expect(screen.getByTestId("manual-hint")).toHaveTextContent(
      "The robot is moving.",
    );
  });

  it("locks in a fault", () => {
    renderPanel(statusFixture({ state: "fault", step: "Fault", fault: "boom" }));

    expect(screen.getByRole("button", { name: "Jog X positive" })).toBeDisabled();
    expect(screen.getByTestId("manual-hint")).toHaveTextContent(
      "Reset the fault",
    );
  });

  it("locks when disconnected or pending", () => {
    const first = renderPanel(statusFixture(), { connected: false });
    expect(screen.getByRole("button", { name: "Jog X positive" })).toBeDisabled();
    expect(screen.getByTestId("manual-hint")).toHaveTextContent(
      "Live connection lost",
    );
    first.unmount();

    renderPanel(statusFixture(), { pending: "jog-x" });
    expect(screen.getByRole("button", { name: "Jog X positive" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Open gripper" })).toBeDisabled();
  });
});
