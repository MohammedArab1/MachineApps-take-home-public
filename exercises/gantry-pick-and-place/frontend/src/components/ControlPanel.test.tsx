import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ControlPanel } from "./ControlPanel";
import { position, statusFixture } from "../test/fixtures";

function renderPanel(
  status = statusFixture(),
  overrides: Partial<Parameters<typeof ControlPanel>[0]> = {},
) {
  const props = {
    status,
    connected: true,
    pending: null,
    devTools: false,
    onHome: vi.fn(),
    onStart: vi.fn(),
    onResume: vi.fn(),
    onStop: vi.fn(),
    onReset: vi.fn(),
    onSimulateFault: vi.fn(),
    ...overrides,
  };
  const result = render(<ControlPanel {...props} />);
  return { ...result, props };
}

describe("ControlPanel", () => {
  it("enables Start and Home when ready", () => {
    renderPanel();

    expect(screen.getByRole("button", { name: "Start sequence" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Home robot" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Stop" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reset fault" })).toBeDisabled();
    expect(screen.getByTestId("control-hint")).toHaveTextContent(
      "Ready for the next command.",
    );
  });

  it("enables Stop while busy and disables Start and Home", () => {
    renderPanel(
      statusFixture({
        busy: true,
        state: "Cycle_moveToPick",
        step: "Moving to cube",
      }),
    );

    expect(screen.getByRole("button", { name: "Start sequence" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Home robot" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Stop" })).toBeEnabled();
    expect(screen.getByTestId("control-hint")).toHaveTextContent(
      "An operation is running.",
    );
  });

  it("enables Reset in a fault and disables motion commands", () => {
    renderPanel(
      statusFixture({ state: "fault", step: "Fault", fault: "boom" }),
    );

    expect(screen.getByRole("button", { name: "Start sequence" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Home robot" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reset fault" })).toBeEnabled();
    expect(screen.getByTestId("control-hint")).toHaveTextContent(
      "The robot is faulted.",
    );
  });

  it("disables Start and Home when disconnected but keeps Stop available", () => {
    renderPanel(
      statusFixture({
        busy: true,
        state: "Cycle_moveToPick",
        step: "Moving to cube",
      }),
      { connected: false },
    );

    expect(screen.getByRole("button", { name: "Start sequence" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Home robot" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Stop" })).toBeEnabled();
    expect(screen.getByTestId("control-hint")).toHaveTextContent(
      "Live connection lost.",
    );
  });

  it("enables Start with a closed gripper at Table A", () => {
    renderPanel(statusFixture({ gripper: "closed" }));

    expect(screen.getByRole("button", { name: "Start sequence" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Home robot" })).toBeEnabled();
    expect(screen.getByTestId("control-hint")).toHaveTextContent(
      "It will open when the sequence starts.",
    );
  });

  it("disables Start when the cube is not at Table A", () => {
    renderPanel(
      statusFixture({ cubeLocation: "table_b", cubePosition: position(630, -550, 0) }),
    );

    expect(screen.getByRole("button", { name: "Start sequence" })).toBeDisabled();
    expect(screen.getByTestId("control-hint")).toHaveTextContent(
      "The cube is on Table B. Reset it to Table A first.",
    );
  });

  it("offers Resume when a stopped sequence is holding the cube", async () => {
    const user = userEvent.setup();
    const held = renderPanel(
      statusFixture({
        gripper: "closed",
        cubeLocation: "held",
        cubePosition: position(-650, 650, 0),
      }),
    );

    const resume = screen.getByRole("button", { name: "Resume sequence" });
    expect(resume).toBeEnabled();
    expect(
      screen.queryByRole("button", { name: "Start sequence" }),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("control-hint")).toHaveTextContent(
      "Resume to finish placing it.",
    );

    await user.click(resume);
    expect(held.props.onResume).toHaveBeenCalledOnce();
    expect(held.props.onStart).not.toHaveBeenCalled();
  });

  it("shows a pending Resume label", () => {
    renderPanel(
      statusFixture({
        gripper: "closed",
        cubeLocation: "held",
        cubePosition: position(-650, 650, 0),
      }),
      { pending: "resume" },
    );

    const resume = screen.getByRole("button", { name: "Resume sequence…" });
    expect(resume).toBeDisabled();
    expect(resume).toHaveAttribute("aria-busy", "true");
  });

  it("keeps Start disabled when the cube is held but the gripper is open", () => {
    renderPanel(
      statusFixture({
        gripper: "open",
        cubeLocation: "held",
        cubePosition: position(-650, 650, 0),
      }),
    );

    expect(screen.getByRole("button", { name: "Start sequence" })).toBeDisabled();
    expect(
      screen.queryByRole("button", { name: "Resume sequence" }),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("control-hint")).toHaveTextContent(
      "The cube is in the gripper but the gripper is open. Reset it to Table A first.",
    );
  });

  it("invokes the command callbacks", async () => {
    const user = userEvent.setup();
    const first = renderPanel();

    await user.click(screen.getByRole("button", { name: "Start sequence" }));
    await user.click(screen.getByRole("button", { name: "Home robot" }));
    expect(first.props.onStart).toHaveBeenCalledOnce();
    expect(first.props.onHome).toHaveBeenCalledOnce();
    first.unmount();

    const busy = statusFixture({
      busy: true,
      state: "Cycle_moveToPick",
      step: "Moving to cube",
    });
    const second = renderPanel(busy, { onStop: first.props.onStop });
    await user.click(screen.getByRole("button", { name: "Stop" }));
    expect(first.props.onStop).toHaveBeenCalledOnce();
    second.unmount();

    const faulted = statusFixture({ state: "fault", step: "Fault" });
    const third = renderPanel(faulted, { onReset: first.props.onReset });
    await user.click(screen.getByRole("button", { name: "Reset fault" }));
    expect(first.props.onReset).toHaveBeenCalledOnce();
    third.unmount();
  });

  it("shows pending labels and disables every command", () => {
    renderPanel(statusFixture(), { pending: "start" });

    const start = screen.getByRole("button", { name: "Start sequence…" });
    expect(start).toBeDisabled();
    expect(start).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("button", { name: "Home robot" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Stop" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reset fault" })).toBeDisabled();
  });

  it("renders developer tools only when enabled", async () => {
    const user = userEvent.setup();
    const panel = renderPanel(statusFixture(), { devTools: true });

    expect(screen.getByText("Developer tools")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Simulate fault" }));
    expect(panel.props.onSimulateFault).toHaveBeenCalledOnce();
  });

  it("hides developer tools by default", () => {
    renderPanel();
    expect(screen.queryByText("Developer tools")).not.toBeInTheDocument();
  });

  it("disables the fault simulator while faulted", () => {
    renderPanel(statusFixture({ state: "fault", step: "Fault" }), {
      devTools: true,
    });
    expect(
      screen.getByRole("button", { name: "Simulate fault" }),
    ).toBeDisabled();
  });
});
