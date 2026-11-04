import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConfigForm } from "./ConfigForm";
import type { CommandMessage, ConfigValues } from "../types";
import { configFixture, position } from "../test/fixtures";

interface RenderOptions {
  config?: ReturnType<typeof configFixture>;
  connected?: boolean;
  busy?: boolean;
  onSave?: (values: ConfigValues) => Promise<CommandMessage>;
}

function renderForm(options: RenderOptions = {}) {
  const onSave = vi.fn(
    options.onSave ??
      (async () => ({ ok: true, message: "Configuration saved" })),
  );
  const props = {
    config: options.config ?? configFixture(),
    connected: options.connected ?? true,
    busy: options.busy ?? false,
    onSave,
  };
  const result = render(<ConfigForm {...props} />);
  return { ...result, props, onSave };
}

describe("ConfigForm", () => {
  it("starts saved and disabled until edited", () => {
    renderForm();

    expect(screen.getByLabelText("Cube X")).toHaveValue(-750);
    expect(screen.getByLabelText("Destination X")).toHaveValue(700);
    expect(screen.getByLabelText("Home Z")).toHaveValue(0);
    expect(screen.getByLabelText("Speed (mm/s)")).toHaveValue(90);
    expect(screen.getByLabelText("Approach height (mm)")).toHaveValue(100);
    expect(screen.getByText("Saved")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Save configuration" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Discard changes" }),
    ).toBeDisabled();
  });

  it("saves the complete configuration", async () => {
    const user = userEvent.setup();
    const { onSave } = renderForm();

    const cubeX = screen.getByLabelText("Cube X");
    await user.clear(cubeX);
    await user.type(cubeX, "-500");
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Save configuration" }),
    );

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
    expect(onSave.mock.calls[0][0]).toEqual({
      cube: { x: "-500", y: "750", z: "0" },
      destination: { x: "700", y: "-700", z: "0" },
      home: { x: "0", y: "0", z: "0" },
      speed: "90",
      approachHeight: "100",
    });
    expect(await screen.findByTestId("config-message")).toHaveTextContent(
      "Configuration saved",
    );
    expect(screen.getByText("Saved")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Save configuration" }),
    ).toBeDisabled();
  });

  it("shows validation errors and blocks saving", async () => {
    const user = userEvent.setup();
    const { onSave } = renderForm();

    const cubeX = screen.getByLabelText("Cube X");
    await user.clear(cubeX);

    expect(screen.getByText("Enter a number.")).toBeInTheDocument();
    expect(cubeX).toHaveAttribute("aria-invalid", "true");
    expect(
      screen.getByRole("button", { name: "Save configuration" }),
    ).toBeDisabled();

    await user.click(
      screen.getByRole("button", { name: "Save configuration" }),
    );
    expect(onSave).not.toHaveBeenCalled();
  });

  it("shows a server rejection and keeps the form dirty", async () => {
    const user = userEvent.setup();
    const onSave = vi
      .fn()
      .mockResolvedValue({ ok: false, message: "Server says no" });
    renderForm({ onSave });

    const speed = screen.getByLabelText("Speed (mm/s)");
    await user.clear(speed);
    await user.type(speed, "50");
    await user.click(
      screen.getByRole("button", { name: "Save configuration" }),
    );

    expect(await screen.findByTestId("config-message")).toHaveTextContent(
      "Server says no",
    );
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  });

  it("shows a network rejection", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockRejectedValue(new Error("connection refused"));
    renderForm({ onSave });

    const speed = screen.getByLabelText("Speed (mm/s)");
    await user.clear(speed);
    await user.type(speed, "50");
    await user.click(
      screen.getByRole("button", { name: "Save configuration" }),
    );

    expect(await screen.findByTestId("config-message")).toHaveTextContent(
      "connection refused",
    );
  });

  it("discards edits", async () => {
    const user = userEvent.setup();
    renderForm();

    const cubeX = screen.getByLabelText("Cube X");
    await user.clear(cubeX);
    await user.type(cubeX, "-500");
    await user.click(screen.getByRole("button", { name: "Discard changes" }));

    expect(screen.getByLabelText("Cube X")).toHaveValue(-750);
    expect(screen.getByText("Saved")).toBeInTheDocument();
  });

  it("syncs server changes while clean and preserves edits while dirty", async () => {
    const user = userEvent.setup();
    const { rerender } = renderForm();

    rerender(
      <ConfigForm
        config={configFixture({
          cubePosition: position(-600, 600, 0),
        })}
        connected
        busy={false}
        onSave={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("Cube X")).toHaveValue(-600);

    const cubeX = screen.getByLabelText("Cube X");
    await user.clear(cubeX);
    await user.type(cubeX, "-500");

    rerender(
      <ConfigForm
        config={configFixture({
          cubePosition: position(-400, 400, 0),
        })}
        connected
        busy={false}
        onSave={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("Cube X")).toHaveValue(-500);
  });

  it("disables the form while busy or disconnected", () => {
    const { unmount } = renderForm({ busy: true });
    expect(screen.getByLabelText("Cube X")).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Save configuration" }),
    ).toBeDisabled();
    unmount();

    renderForm({ connected: false });
    expect(screen.getByLabelText("Cube X")).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Save configuration" }),
    ).toBeDisabled();
  });
});
