# Gantry Pick & Place

A proof-of-concept 3-axis gantry robot controller with a FastAPI backend and a
React/TypeScript operator dashboard. The robot picks a cube from **Table A**,
carries it across the cell, and places it on **Table B** using the provided
`robot_sim.py` simulator.

The backend uses:

- [`vention-communication`](https://pypi.org/project/vention-communication/) for
  Connect-style RPC actions and server-streaming telemetry.
- [`vention-state-machine`](https://pypi.org/project/vention-state-machine/) for
  the robot control state machine.
- [`vention-storage`](https://pypi.org/project/vention-storage/) for persisting
  the machine configuration in SQLite.

The frontend uses the TypeScript client generated from the proto emitted by
`vention-communication`; it never polls for live state.

![Dashboard showing the cell view, telemetry, controls, configuration, and activity log](docs/dashboard.png)

## Demo

A silent, captioned 140-second walkthrough is available as
[MP4](docs/demo.mp4), [WebM](docs/demo.webm), or [GIF](docs/demo.gif). It shows
the modeled cube following the gripper from Table A to Table B, the longer step
pauses, and fault recovery.

---

## Quick start

### Docker Compose (recommended)

```bash
docker compose up --build
```

- Dashboard: <http://localhost:3000>
- Backend health: <http://localhost:8000/health>

The frontend nginx container proxies `/rpc` to the backend with buffering
disabled so the telemetry stream works through the proxy. The SQLite database
lives in the `gantry-data` volume, so the configuration survives restarts.

The production container has the developer fault simulator disabled. To use
it, run locally (below) or set `GANTRY_ENABLE_DEV_TOOLS=true` on the backend and
build the frontend in dev mode.

### Local development

The Vention libraries require **Python 3.10** (`>=3.10,<3.11`).

```bash
# backend
cd backend
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000

# frontend (in another terminal)
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/rpc` to
`http://localhost:8000`, so no CORS configuration is needed for the normal
development flow.

### Tests and checks

```bash
# backend: 176 tests, ~96.2% coverage, ruff
cd backend
.venv/bin/ruff check app tests
.venv/bin/pytest --cov=app --cov-report=term-missing

# frontend: 94 tests, ~95.7% coverage, lint, typecheck, build
cd frontend
npm run lint
npm run typecheck
npm run test:coverage
npm run build
```

Or from the project root:

```bash
make test
make lint
make build
```

---

## What the dashboard does

- **Live telemetry** from the `Status` stream: robot X/Y/Z, gripper state,
  moving/idle, raw state-machine state, friendly step, cycle progress, cube
  location and live position, and the configured cube/destination/home
  positions.
- **Cell view**: an SVG plan view of the 2 m × 2 m footprint with Table A,
  Table B, the robot base and current position, the modeled cube, the
  destination, and a vertical Z gauge. The cube follows the gripper while it is
  held.
- **Controls**: Home, Start/Resume, Stop, and Reset, plus a **Cube** panel with
  **Return cube to Table A**. There are no manual jog or gripper controls in the
  dashboard. Motion commands are enabled only when the robot is idle and not
  faulted; Stop remains available while an operation is running, even if the
  telemetry stream drops. Start is disabled unless the cube is on Table A; if
  the gripper is closed with no cube held, it opens automatically when the
  sequence starts. If Stop leaves the cube held, the primary button becomes
  **Resume sequence** to finish the placement.
- **Configuration**: cube start, destination, home, speed, and approach height.
  The form validates locally and the server validates again. Configuration is
  persisted through `vention-storage`.
- **Error and connection states**: a red fault banner with Reset, a connection
  banner with automatic stream reconnect, and a dismissible command result
  alert.
- **Activity log**: the `Events` stream plus `RecentEvents` on reconnect, so the
  log is not empty after a page reload.

---

## Coordinate convention

The application uses a robot-centred Cartesian frame in millimetres:

| Item | Convention |
| --- | --- |
| Origin | Robot base centre |
| +X | Right in the plan view |
| +Y | Up/away in the plan view |
| +Z | Up |
| Workspace | `x, y, z ∈ [-1000, 1000]` (the simulator's limits) |
| Footprint | 2000 × 2000 mm |
| Table A | 500 mm square, inset ~100 mm from the top/left: `x ∈ [-900, -400]`, `y ∈ [400, 900]` |
| Table B | 500 mm square rotated 45°, centre `(630, -550)`; right corner near the right edge, bottom corner inset ~100 mm |

Defaults:

```json
{
  "cubePosition":        { "x": -650, "y":  650, "z": 0 },
  "destinationPosition": { "x":  630, "y": -550, "z": 0 },
  "homePosition":        { "x":    0, "y":    0, "z": 0 },
  "speed": 90,
  "approachHeight": 100
}
```

Validation rules:

- Every position must be finite and within ±1000 mm on each axis.
- Cube and destination `z >= 0` (the table surface), and
  `z + approachHeight <= 1000`.
- Home may be anywhere within the workspace, including negative Z.
- Speed is an integer from 1 to 100 mm/s. Speed 0 is rejected because
  `robot_sim.move_to` divides by the planned motion time.
- Approach height is 0 to 1000 mm.

The dashboard draws Table B as a 500 mm square rotated 45°, matching the
figure: its right corner sits close to the right cell edge and its bottom
corner is inset ~100 mm. The configured coordinates are authoritative.

---

## Sequence

The required sequence is modelled as eight explicit leaf states:

```mermaid
stateDiagram-v2
    [*] --> ready
    ready --> Cycle_moveToPick: start
    ready --> Recovery_moveToPlace: resume
    Recovery_moveToPlace --> Cycle_lowerToPlace: next
    Cycle_moveToPick --> Cycle_lowerToPick: next
    Cycle_lowerToPick --> Cycle_closeGripper: next
    Cycle_closeGripper --> Cycle_liftFromPick: next
    Cycle_liftFromPick --> Cycle_moveToPlace: next
    Cycle_moveToPlace --> Cycle_lowerToPlace: next
    Cycle_lowerToPlace --> Cycle_openGripper: next
    Cycle_openGripper --> Cycle_liftFromPlace: next
    Cycle_liftFromPlace --> ready: next

    ready --> Homing_moveHome: home
    Homing_moveHome --> ready: homed
    ready --> Manual_move: set position
    Manual_move --> ready: moved

    ready --> fault: fail
    Cycle_moveToPick --> fault: fail
    Cycle_lowerToPick --> fault: fail
    Cycle_closeGripper --> fault: fail
    Cycle_liftFromPick --> fault: fail
    Cycle_moveToPlace --> fault: fail
    Cycle_lowerToPlace --> fault: fail
    Cycle_openGripper --> fault: fail
    Cycle_liftFromPlace --> fault: fail
    Recovery_moveToPlace --> fault: fail
    Homing_moveHome --> fault: fail
    Manual_move --> fault: fail
    fault --> ready: reset
```

| Step | Target |
| --- | --- |
| Move to cube | `(cube.x, cube.y, cube.z + approachHeight)` |
| Lower to cube | `(cube.x, cube.y, cube.z)` |
| Close gripper | — |
| Lift cube | `(cube.x, cube.y, cube.z + approachHeight)` |
| Move to destination | `(dest.x, dest.y, dest.z + approachHeight)` |
| Lower to destination | `(dest.x, dest.y, dest.z)` |
| Open gripper | — |
| Lift from destination | `(dest.x, dest.y, dest.z + approachHeight)` → `ready` |

The sequence ends with the cube on Table B and the robot lifted above it. Home
is a separate command.

Cube state is tracked independently: it moves from `table_a` to `held` when the
gripper closes at the pick, and from `held` to `table_b` when the gripper opens
at the destination. Start is rejected unless the cube is back on Table A;
`ResetCube` returns it there for another run.

If **Stop** interrupts the cycle after the pick, the cube remains held and the
gripper remains closed. **Resume sequence** lifts straight up at the current
X/Y to a safe travel height, moves to the Table B approach point, then joins the
normal lower, open, and lift steps. It never re-picks from Table A and never
drags the cube sideways along a table. If Stop happened before the pick, the
cube is still on Table A and the normal Start action is available.

`GANTRY_STEP_PAUSE_S` adds a deliberate pause after every motion or gripper step
(default `0`; the recorded demo uses `4`). `GANTRY_GRIPPER_SETTLE_S` controls the
gripper settle delay (default `0.15`).

Each motion state's synchronous `on_enter` callback schedules an async step
task. The task calls `robot.move_to(...)` repeatedly until the simulator
reports the target is reached and the axis speed is zero, with a computed
timeout. This is the requirement's "call `move_to` repeatedly until motion is
complete" handled inside the state machine callbacks.

---

## API

All application traffic uses Connect RPC under `/rpc`:

| RPC | Kind | Request | Response |
| --- | --- | --- | --- |
| `GetStatus` | action | `Empty` | `StatusSnapshot` |
| `GetConfig` | action | `Empty` | `MachineConfig` |
| `SetConfig` | action | `SetConfigRequest` | `ActionResult` |
| `GetRobotPosition` | action | `Empty` | `RobotState` |
| `SetRobotPosition` | action | `MoveRobotRequest` | `ActionResult` |
| `ResetCube` | action | `Empty` | `ActionResult` |
| `HomeRobot` | action | `Empty` | `ActionResult` |
| `StartSequence` | action | `Empty` | `ActionResult` |
| `ResumeSequence` | action | `Empty` | `ActionResult` |
| `StopSequence` | action | `Empty` | `ActionResult` |
| `Reset` | action | `Empty` | `ActionResult` |
| `RecentEvents` | action | `Empty` | `EventList` |
| `SimulateFault` | action | `Empty` | `ActionResult` (dev tool) |
| `Status` | stream | `Empty` | `StatusSnapshot` |
| `Events` | stream | `Empty` | `Event` |

`SetRobotPosition` is an absolute position move through the same state machine,
not a teleport. It remains API-only to satisfy the required Get/Set robot
position surface; the dashboard does not expose manual motion or gripper
controls. `ResetCube` returns the simulated cube to Table A and requires an open
gripper. `StartSequence` is rejected unless the cube is on Table A; it opens a
closed gripper automatically before moving, because no cube is held in that
state. `ResumeSequence` is accepted only when the machine is ready and a stopped
cycle left the cube held with the gripper closed; it finishes the place without
re-picking.

Every command returns:

```json
{
  "ok": true,
  "message": "Sequence started",
  "status": { "...": "the latest status snapshot" }
}
```

Expected domain failures (busy, invalid configuration, fault state, etc.)
return `ok: false` with a human-readable message. This is deliberate: the
pinned `vention-communication` router serializes raised exceptions into an
HTTP 200 error envelope that the generated client cannot distinguish from a
default response, so command handlers return structured results instead.

The proto is committed at `backend/proto/app.proto`. The backend emits it on
import; the frontend regenerates `src/gen/` from it before `dev`, `build`,
`typecheck`, and tests. The CI job regenerates the proto and fails if the
committed file is stale.

### Plain HTTP endpoints

- `GET /health` — Docker/CI health check.
- The storage library also mounts its CRUD routes under `/config` (writes
  require an `X-User` header). The dashboard uses the Connect RPCs, not these
  routes.

---

## Architecture

```
Browser (React 19 + TypeScript + Vite)
  │
  │  generated Connect client
  │  ├── unary actions: commands and queries
  │  └── server streams: Status (replay latest) and Events (FIFO)
  ▼
FastAPI + VentionApp (one uvicorn worker)
  │
  ├── app/api.py        @action handlers (structured results)
  ├── app/telemetry.py  @stream publishers + heartbeat
  ├── app/service.py    command serialization, validation, events
  ├── app/machine.py    PickAndPlaceMachine (vention-state-machine)
  ├── app/robot.py      RobotDriver protocol + SimRobotDriver
  ├── app/repository.py ConfigRepository + vention-storage/SQLite
  └── robot_sim.py      provided simulator, unchanged
```

### Backend layout

```
backend/
├── robot_sim.py                  # provided, unchanged
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml                # pytest + coverage + ruff
├── proto/app.proto               # generated and committed
├── app/
│   ├── config.py                 # environment settings
│   ├── models.py                 # Pydantic API/domain models
│   ├── robot.py                  # simulator adapter
│   ├── repository.py             # SQLite + in-memory repositories
│   ├── machine.py                # state machine + sequence
│   ├── telemetry.py              # streams + heartbeat
│   ├── service.py                # orchestration and command rules
│   ├── api.py                    # Connect actions
│   └── main.py                   # wiring, lifespan, proto emission
└── tests/                        # 176 tests
```

### Frontend layout

```
frontend/
├── src/
│   ├── app.tsx                   # dashboard wiring
│   ├── client.ts                 # generated Connect client
│   ├── use-stream.ts             # reconnect + stall detection hook
│   ├── components/               # SceneView, TelemetryPanel, ConfigForm, ...
│   ├── lib/                      # formatting, validation, scene math, events
│   ├── gen/                      # generated by buf, gitignored
│   └── styles.css
├── buf.gen.yaml
├── nginx.conf
└── Dockerfile
```

---

## Design decisions and trade-offs

### Python 3.10 and exact pins

The Vention packages require Python `>=3.10,<3.11`. The project pins
`vention-communication==0.3.0`, `vention-state-machine==0.3.1`, and
`vention-storage==0.5.4`. Docker uses `python:3.10-slim`; local instructions use
`python3.10`.

### Connect RPC, generated client, no polling

`vention-communication` is a Connect-compatible RPC layer, not a REST or
WebSocket library. The dashboard uses the generated client for every command
and for both streams. Live telemetry is a server stream with `replay=True`, a
latest-only queue, and a 100 ms/1 s heartbeat. The frontend reconnects with
backoff and treats 5 s of silence as a stalled stream.

### Fine-grained state machine and a custom `fail` trigger

Each sequence step is a leaf state so the dashboard can show exactly what the
machine is doing. The pinned `transitions` engine is synchronous, so entry
callbacks are synchronous and schedule async step tasks. The library's built-in
`to_fault` transition has an async before-hook that `transitions` never awaits;
the project uses its own `fail` trigger and cancels tasks explicitly from the
service instead.

State member names are camelCase because the hierarchical state-name separator
is `_`; a member named `move_to_pick` would be parsed as nested states and
crash the machine.

### Structured command results

As noted above, `vention-communication` returns HTTP 200 with an error envelope
for exceptions. Commands therefore return `ActionResult { ok, message, status }`.
The frontend displays both domain rejections and network/timeout errors.

### Robot adapter

`SimRobotDriver` centralizes the simulator's quirks:

- Rejects speed 0 before `move_to` can divide by zero.
- Rejects out-of-limits targets with a domain error.
- Converts the simulator's error string into an exception.
- `halt()` zeroes the simulator's axis speed so an interrupted move does not
  continue with its old velocity on the next command.
- Motion loops require both "at target" and "not moving", so the simulator gets
  the extra call it needs to snap exactly to the target and zero its speed.

### Persistence

Two single-row SQLModel tables are persisted through `vention-storage`:

- `gantry_config` — cube, destination, home, speed, and approach height.
- `gantry_run_state` — status, operation, state, step, last robot position,
  gripper state, fault message, and timestamp.

`bootstrap` creates both tables; the `ModelAccessor` reads and writes them with
audit logging. The repository protocols have in-memory implementations so
unit/API tests do not depend on SQLite. If a config row is invalid, the app logs
a warning, falls back to defaults, and rewrites it.

The run state is updated on every state transition and on safe shutdown. On
startup:

- `running` or `interrupted` → the machine enters `fault` with a message naming
  the interrupted step and last known position; the operator must inspect the
  cell and press Reset.
- `fault` → the fault is restored, so a fault is never silently cleared by a
  restart.
- `idle` → the machine starts ready, with the persisted gripper state restored.

The app never auto-resumes motion. The run state is a safety record, not a
durable execution engine. A hard kill (SIGKILL) cannot run cleanup, but the last
persisted `running` record still forces a fault on the next start.

The FastAPI lifespan cancels the telemetry and step tasks, halts the simulator,
and records `interrupted` if an operation was active. The robot is left stopped
where it was; the simulator starts at the configured home on the next process
start. A real machine would need an explicit re-home and hardware safety
checks.

### One uvicorn worker

The robot, state machine, telemetry loop, and SQLite configuration are
process-local. Running multiple workers would create multiple independent
robots and split the telemetry stream, so the Docker command and documentation
use exactly one worker.

### Custom dashboard instead of an HMI component library

The dashboard uses React 19 + Vite + custom CSS and an SVG plan view. This
keeps the bundle small, avoids React 17 peer constraints from Vention's
pendant-oriented UI packages, and makes the scene math easy to test. The
provided figure is a 2D plan view; a 2D SVG is the clearest representation.

### Testing strategy

- **Backend:** 176 tests. A deterministic `FakeRobot` exercises the state
  machine without sleeping; the real simulator adapter is tested with a patched
  clock; the SQLite repositories are tested with a temporary database and a
  simulated restart; the Connect actions are exercised through the real ASGI
  app; a real uvicorn subprocess verifies the stream framing; the proto is
  checked against the Python surface. Coverage is ~96.2% of `app/`.
- **Frontend:** 94 tests with Vitest + React Testing Library. Scene math,
  validation, event merging, every component state, the cube panel, the
  stream hook's reconnect/stall/unmount behavior, and the app's loading/
  connected/fault/disconnected flows. Coverage is ~95.7%.
- **CI:** GitHub Actions runs backend lint/tests/proto check and frontend
  lint/typecheck/coverage/build on every push and pull request.

### Assumptions and limitations

- This is a simulation: no real hardware, collision detection, inverse
  kinematics, or safety PLC.
- The cube is modeled as a simple stateful object (`table_a`, `held`, `table_b`,
  `unknown`) and drawn at the configured pick point or the live gripper
  position. Its physical dimensions, rotation, and collision volume are not
  simulated.
- The table geometry is a visual reference. Motion targets come from the
  configured cube and destination points, not from the table polygons, so the
  table placement does not affect the control logic. The defaults are the
  measured table centres.
- The run state is persisted, but motion is never auto-resumed. An interrupted
  operation comes up in `fault` and requires Reset. A real machine additionally
  needs an explicit re-home and hardware safety checks.
- Start requires the cube on Table A. If the gripper is closed with no cube
  held, Start opens it automatically before moving. If the cube is held, Start
  is rejected and Resume is the safe way to finish the placement.
- A Stop after the pick leaves the cube held. Resume is an explicit safe
  recovery: lift at the current X/Y, move to the place approach, and finish the
  placement. Motion is never auto-resumed, and an interrupted run still starts
  in `fault` and requires Reset before Resume or any other command.
- The dashboard deliberately has no manual jog or gripper controls. The required
  `SetRobotPosition` endpoint remains available for API clients, but it is not
  exposed in the UI.
- One operator, one browser, one backend worker, no authentication.
- The `SimulateFault` action is a demo aid. It is always in the proto but the
  backend refuses it when `GANTRY_ENABLE_DEV_TOOLS=false`; the frontend hides
  the button outside Vite dev mode.
- The storage CRUD routes are mounted by `vention-storage`; they are not part of
  the dashboard's flow.

---

## Demo walkthrough

1. `docker compose up --build` (or run the backend and `npm run dev` locally).
2. Open the dashboard. The robot starts at home `(0, 0, 0)`; the cube is at
   Table A and the destination at Table B.
3. Click **Start sequence**. Watch the state badge, step label, X/Y/Z readouts,
   scene markers, cube location, and progress bar advance through the eight
   steps. The cube follows the gripper ring while it is held.
4. The sequence ends with the cube on Table B and the robot lifted above it.
   Click **Home robot** to return.
5. To run again, click **Return cube to Table A**, then **Start sequence**.
   Edit the cube or destination coordinates and click **Save configuration**.
   Reload the page; the values are restored from SQLite.
6. Start a sequence, stop the server mid-operation, and start it again. The
   dashboard comes up in `fault` with an interrupted-operation message; press
   **Reset fault** to recover.
7. In local dev, open **Developer tools → Simulate fault** to see the red fault
   banner, then click **Reset fault**.
8. Click **Stop** during a sequence to halt at the current position. If the
   cube was already picked up, the primary button becomes **Resume sequence**;
   click it to lift clear, move to Table B, and finish placing the cube. If the
   stop happened before the pick, **Start sequence** remains available.

---

## Submission checklist

- [x] `vention-communication` Connect RPC + streams
- [x] `vention-state-machine` control logic
- [x] Provided `robot_sim.py` used unchanged; `move_to` polled to completion
- [x] Get/Set robot, cube, destination, home; Home, Start, Get Status
- [x] Full pick-and-place sequence
- [x] Modeled cube follows the sequence and can be reset
- [x] Safe Resume after Stop with the cube held
- [x] Dashboard telemetry, controls, error/state visuals
- [x] `vention-storage` persistence across restarts
- [x] Backend and frontend tests
- [x] Docker Compose single command
- [x] README with setup, design decisions, assumptions, trade-offs
