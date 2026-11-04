import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ActivityLog } from "./ActivityLog";
import { eventFixture } from "../test/fixtures";

describe("ActivityLog", () => {
  it("shows an empty state and disables Clear", () => {
    render(<ActivityLog events={[]} onClear={vi.fn()} />);

    expect(screen.getByTestId("activity-empty")).toHaveTextContent(
      "No events yet.",
    );
    expect(screen.getByRole("button", { name: "Clear" })).toBeDisabled();
  });

  it("renders events with levels, times, and details", () => {
    render(
      <ActivityLog
        events={[
          eventFixture({
            id: 2,
            message: "Sequence complete",
            level: "warning",
            detail: "Took 4.2 s",
          }),
          eventFixture({ id: 1, message: "Sequence started" }),
        ]}
        onClear={vi.fn()}
      />,
    );

    expect(screen.getByTestId("activity-list")).toBeInTheDocument();
    expect(screen.getByText("Sequence complete")).toBeInTheDocument();
    expect(screen.getByText("Sequence started")).toBeInTheDocument();
    expect(screen.getByText("warning")).toBeInTheDocument();
    expect(screen.getByText("Took 4.2 s")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear" })).toBeEnabled();
  });

  it("calls Clear", async () => {
    const user = userEvent.setup();
    const onClear = vi.fn();
    render(<ActivityLog events={[eventFixture()]} onClear={onClear} />);

    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(onClear).toHaveBeenCalledOnce();
  });
});
