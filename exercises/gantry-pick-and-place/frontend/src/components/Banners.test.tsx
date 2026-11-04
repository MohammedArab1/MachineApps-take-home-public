import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  CommandAlert,
  ConnectionBanner,
  FaultBanner,
} from "./Banners";

describe("FaultBanner", () => {
  it("shows the fault message and resets", async () => {
    const user = userEvent.setup();
    const onReset = vi.fn();
    render(
      <FaultBanner message="gripper stuck" disabled={false} onReset={onReset} />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("gripper stuck");
    await user.click(screen.getByRole("button", { name: "Reset fault" }));
    expect(onReset).toHaveBeenCalledOnce();
  });

  it("uses a generic message and can be disabled", () => {
    render(<FaultBanner message="" disabled onReset={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The state machine is in a fault state.",
    );
    expect(screen.getByRole("button", { name: "Reset fault" })).toBeDisabled();
  });
});

describe("ConnectionBanner", () => {
  it("renders nothing while connected", () => {
    const { container } = render(<ConnectionBanner connected />);
    expect(container).toBeEmptyDOMElement();
  });

  it("warns while disconnected", () => {
    render(<ConnectionBanner connected={false} />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Live connection lost",
    );
  });
});

describe("CommandAlert", () => {
  it("renders success and dismisses", async () => {
    const user = userEvent.setup();
    const onDismiss = vi.fn();
    render(
      <CommandAlert
        message={{ ok: true, message: "Sequence started" }}
        onDismiss={onDismiss}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Command accepted");
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("renders an error alert", () => {
    render(
      <CommandAlert
        message={{ ok: false, message: "An operation is already running" }}
        onDismiss={vi.fn()}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Command rejected");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "An operation is already running",
    );
  });
});
