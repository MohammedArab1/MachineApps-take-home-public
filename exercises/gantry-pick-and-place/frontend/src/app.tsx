import { useCallback, useEffect, useState } from "react";

import {
  homeRobot,
  openEvents,
  openStatus,
  recentEvents as fetchRecentEvents,
  resetCube,
  resetRobot,
  resumeSequence,
  setConfig as sendConfig,
  simulateFault,
  startSequence,
  stopSequence,
} from "./client";
import { useStream } from "./use-stream";
import { ActivityLog } from "./components/ActivityLog";
import {
  CommandAlert,
  ConnectionBanner,
  FaultBanner,
} from "./components/Banners";
import { ConfigForm } from "./components/ConfigForm";
import { ControlPanel } from "./components/ControlPanel";
import { CubePanel } from "./components/CubePanel";
import { SceneView } from "./components/SceneView";
import { TelemetryPanel } from "./components/TelemetryPanel";
import { mergeEvents } from "./lib/events";
import { formatTime } from "./lib/format";
import { configToPayload } from "./lib/validation";
import type {
  ActionResult,
  CommandMessage,
  ConfigValues,
  Event,
  StatusSnapshot,
} from "./types";

const STATUS_STALL_MS = 5_000;

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "The command could not be completed.";
}

function LoadingScreen({ connected }: { connected: boolean }) {
  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <p className="eyebrow">3-axis gantry · proof of concept</p>
          <h1>Pick &amp; Place</h1>
        </div>
        <div className="header-meta">
          <span
            className={`connection ${connected ? "connection--live" : "connection--down"}`}
          >
            <span className="connection-dot" />
            {connected ? "Live" : "Connecting"}
          </span>
        </div>
      </header>
      <main className="loading" aria-live="polite">
        <div className="spinner" aria-hidden="true" />
        <h2>
          {connected
            ? "Waiting for telemetry…"
            : "Connecting to the robot controller…"}
        </h2>
        <p>
          The dashboard opens as soon as the status stream sends its first
          frame.
        </p>
      </main>
    </div>
  );
}

export function App() {
  const { value: status, connected } = useStream<StatusSnapshot>(openStatus, {
    stallMs: STATUS_STALL_MS,
  });
  const [events, setEvents] = useState<Event[]>([]);
  const [pending, setPending] = useState<string | null>(null);
  const [commandMessage, setCommandMessage] = useState<CommandMessage | null>(
    null,
  );

  useStream<Event>(openEvents, {
    onMessage: (event) => {
      setEvents((previous) => mergeEvents(previous, [event]));
    },
  });

  useEffect(() => {
    let cancelled = false;
    fetchRecentEvents()
      .then((list) => {
        if (!cancelled) {
          setEvents((previous) => mergeEvents(previous, list.events));
        }
      })
      .catch(() => {
        // The status stream's connection banner is the user-facing signal.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const runCommand = useCallback(
    async (name: string, command: () => Promise<ActionResult>) => {
      setPending(name);
      setCommandMessage(null);
      try {
        const result = await command();
        setCommandMessage({ ok: result.ok, message: result.message });
      } catch (error) {
        setCommandMessage({ ok: false, message: errorMessage(error) });
      } finally {
        setPending(null);
      }
    },
    [],
  );

  const handleSaveConfig = useCallback(
    async (values: ConfigValues): Promise<CommandMessage> => {
      const payload = configToPayload(values);
      if (!payload) {
        return { ok: false, message: "The configuration is invalid." };
      }
      setPending("config");
      try {
        const result = await sendConfig(payload);
        return { ok: result.ok, message: result.message };
      } catch (error) {
        return { ok: false, message: errorMessage(error) };
      } finally {
        setPending(null);
      }
    },
    [],
  );

  if (!status) return <LoadingScreen connected={connected} />;

  const faulted = status.state === "fault";
  const devTools = import.meta.env.DEV;

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <p className="eyebrow">3-axis gantry · proof of concept</p>
          <h1>Pick &amp; Place</h1>
        </div>
        <div className="header-meta">
          <span
            className={`connection ${connected ? "connection--live" : "connection--down"}`}
            data-testid="connection-state"
          >
            <span className="connection-dot" />
            {connected ? "Live" : "Reconnecting"}
          </span>
          <span className="header-state">{status.step}</span>
          <span className="header-updated">
            Updated {formatTime(status.updatedAt)}
          </span>
        </div>
      </header>

      <ConnectionBanner connected={connected} />

      {faulted && (
        <FaultBanner
          message={status.fault}
          disabled={pending !== null}
          onReset={() => void runCommand("reset", resetRobot)}
        />
      )}

      {commandMessage && (
        <CommandAlert
          message={commandMessage}
          onDismiss={() => setCommandMessage(null)}
        />
      )}

      <main className="layout">
        <div className="layout-main">
          <SceneView status={status} />
          <TelemetryPanel status={status} />
        </div>

        <aside className="layout-side">
          <ControlPanel
            status={status}
            connected={connected}
            pending={pending}
            devTools={devTools}
            onHome={() => void runCommand("home", homeRobot)}
            onStart={() => void runCommand("start", startSequence)}
            onResume={() => void runCommand("resume", resumeSequence)}
            onStop={() => void runCommand("stop", stopSequence)}
            onReset={() => void runCommand("reset", resetRobot)}
            onSimulateFault={() => void runCommand("fault", simulateFault)}
          />
          <CubePanel
            status={status}
            connected={connected}
            pending={pending}
            onResetCube={() =>
              void runCommand("reset-cube", resetCube)
            }
          />
          <ConfigForm
            config={status.config}
            connected={connected}
            busy={status.busy}
            onSave={handleSaveConfig}
          />
        </aside>

        <ActivityLog events={events} onClear={() => setEvents([])} />
      </main>

      <footer className="app-footer">
        Coordinates in millimetres · robot limits ±1000 mm · Connect RPC over
        vention-communication
      </footer>
    </div>
  );
}
