import { useEffect, useRef, useState } from "react";

export const DEFAULT_RETRY_DELAYS_MS = [500, 1000, 2000, 5000];

export interface UseStreamOptions<T> {
  /** Treat this much silence as a dropped stream (only for heartbeat streams). */
  stallMs?: number;
  /** Backoff between reconnects. Defaults to 500/1000/2000/5000 ms. */
  retryDelaysMs?: number[];
  /** Called for every message, including messages that are not the latest. */
  onMessage?: (value: T) => void;
}

/**
 * Latest message of a server stream, reopened whenever it drops.
 *
 * The `open` callback must be stable (a module-level function), otherwise the
 * effect re-runs on every render.
 */
export function useStream<T>(
  open: (signal: AbortSignal) => AsyncIterable<T>,
  options: UseStreamOptions<T> = {},
): { value: T | undefined; connected: boolean } {
  const { stallMs } = options;
  const retryDelaysMs = options.retryDelaysMs ?? DEFAULT_RETRY_DELAYS_MS;
  const retryKey = retryDelaysMs.join(",");
  const retryRef = useRef(retryDelaysMs);
  const onMessageRef = useRef(options.onMessage);

  useEffect(() => {
    retryRef.current = retryDelaysMs;
    onMessageRef.current = options.onMessage;
  }, [retryDelaysMs, options.onMessage]);

  const [value, setValue] = useState<T | undefined>(undefined);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let attempt = 0;

    const consume = async (): Promise<void> => {
      while (!controller.signal.aborted) {
        const streamController = new AbortController();
        const abortStream = () => streamController.abort();
        controller.signal.addEventListener("abort", abortStream);

        let stallTimer: ReturnType<typeof setTimeout> | undefined;
        const armStallTimer = () => {
          clearTimeout(stallTimer);
          if (stallMs !== undefined) {
            stallTimer = setTimeout(abortStream, stallMs);
          }
        };
        armStallTimer();

        try {
          for await (const message of open(streamController.signal)) {
            attempt = 0;
            armStallTimer();
            setValue(message);
            setConnected(true);
            onMessageRef.current?.(message);
          }
        } catch {
          // A dropped or stalled stream is reopened below.
        }

        clearTimeout(stallTimer);
        controller.signal.removeEventListener("abort", abortStream);
        if (controller.signal.aborted) return;

        setConnected(false);
        const delays = retryRef.current;
        const delay = delays[Math.min(attempt, delays.length - 1)] ?? 0;
        attempt += 1;
        await new Promise((resolve) => setTimeout(resolve, delay));
      }
    };

    void consume();
    return () => controller.abort();
  }, [open, stallMs, retryKey]);

  return { value, connected };
}
