import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useStream, type UseStreamOptions } from "./use-stream";

function hanging(values: string[]) {
  return (signal: AbortSignal): AsyncIterable<string> =>
    (async function* () {
      for (const value of values) yield value;
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

function Harness({
  open,
  options,
}: {
  open: (signal: AbortSignal) => AsyncIterable<string>;
  options?: UseStreamOptions<string>;
}) {
  const { value, connected } = useStream(open, options);
  return (
    <div>
      <span data-testid="value">{value ?? "none"}</span>
      <span data-testid="connected">{String(connected)}</span>
    </div>
  );
}

describe("useStream", () => {
  it("tracks the latest value and connection", async () => {
    const open = vi.fn(hanging(["a", "b"]));
    render(<Harness open={open} />);

    await waitFor(() =>
      expect(screen.getByTestId("value")).toHaveTextContent("b"),
    );
    expect(screen.getByTestId("connected")).toHaveTextContent("true");
    expect(open).toHaveBeenCalledOnce();
  });

  it("calls onMessage for every message, not only the latest", async () => {
    const onMessage = vi.fn();
    render(<Harness open={hanging(["a", "b"])} options={{ onMessage }} />);

    await waitFor(() => expect(onMessage).toHaveBeenCalledTimes(2));
    expect(onMessage).toHaveBeenNthCalledWith(1, "a");
    expect(onMessage).toHaveBeenNthCalledWith(2, "b");
  });

  it("reconnects after a dropped stream", async () => {
    let call = 0;
    const open = vi.fn((signal: AbortSignal) => {
      call += 1;
      if (call === 1) {
        return (async function* () {
          yield "first";
          throw new Error("dropped");
        })();
      }
      return hanging(["second"])(signal);
    });

    render(<Harness open={open} options={{ retryDelaysMs: [0] }} />);

    await waitFor(() =>
      expect(screen.getByTestId("value")).toHaveTextContent("second"),
    );
    expect(open.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("treats silence as a stall and reconnects", async () => {
    let call = 0;
    const open = vi.fn((signal: AbortSignal) => {
      call += 1;
      if (call === 1) return hanging(["first"])(signal);
      return hanging(["second"])(signal);
    });

    render(
      <Harness open={open} options={{ stallMs: 20, retryDelaysMs: [0] }} />,
    );

    await waitFor(
      () => expect(screen.getByTestId("value")).toHaveTextContent("second"),
      { timeout: 1_000 },
    );
    expect(open.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("aborts the stream on unmount", async () => {
    let captured: AbortSignal | undefined;
    const open = vi.fn((signal: AbortSignal) => {
      captured = signal;
      return hanging(["a"])(signal);
    });
    const { unmount } = render(<Harness open={open} />);

    await waitFor(() =>
      expect(screen.getByTestId("value")).toHaveTextContent("a"),
    );
    unmount();

    expect(captured?.aborted).toBe(true);
  });
});
