"""Business orchestration: command serialization, validation, and status."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

from pydantic import ValidationError

from app.config import Settings
from app.machine import PickAndPlaceMachine
from app.models import (
    CUBE_AT_TABLE_A,
    CUBE_AT_TABLE_B,
    CUBE_HELD,
    DEFAULT_CONFIG,
    ActionResult,
    Event,
    EventList,
    MachineConfig,
    MoveRobotRequest,
    Position,
    RobotState,
    RunState,
    SetConfigRequest,
    StatusSnapshot,
    utc_now_iso,
    validation_message,
)
from app.repository import (
    ConfigRepository,
    InMemoryRunStateRepository,
    RunStateRepository,
)
from app.robot import RobotDriver
from app.telemetry import Telemetry, TelemetrySink

logger = logging.getLogger(__name__)


class GantryService:
    """The single owner of the robot, machine, configuration, and event buffer."""

    def __init__(
        self,
        robot: RobotDriver,
        machine: PickAndPlaceMachine,
        repository: ConfigRepository,
        settings: Settings,
        *,
        run_state_repository: RunStateRepository | None = None,
        telemetry: TelemetrySink | None = None,
    ) -> None:
        self.robot = robot
        self.machine = machine
        self.repository = repository
        self.run_state_repository = run_state_repository or InMemoryRunStateRepository()
        self.settings = settings
        try:
            self.config = repository.load()
        except Exception:
            logger.exception("Could not load the configuration; using defaults")
            self.config = DEFAULT_CONFIG
        self.telemetry: TelemetrySink = telemetry or Telemetry(self)
        self._recent_events: deque[Event] = deque(maxlen=100)
        self._event_id = 0
        self._lock = asyncio.Lock()
        self._active_operation = ""
        self._cube_location = CUBE_AT_TABLE_A
        self._last_position_save_at = 0.0

        self.machine.state_listener = self._on_state_change
        self.machine.gripper_listener = self._on_gripper_change
        self._restore_run_state()

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def status(self) -> StatusSnapshot:
        return StatusSnapshot(
            robot_position=Position.from_list(self.robot.current_position),
            gripper=self.robot.gripper,
            moving=self.robot.moving,
            busy=self.machine.busy,
            state=self.machine.state,
            step=self.machine.step,
            fault=self.machine.fault_message,
            progress=self.machine.progress,
            cube_location=self._cube_location,
            cube_position=self._cube_position(),
            config=self.config,
            limits=Position.from_list(self.robot.limits),
            updated_at=utc_now_iso(),
        )

    def robot_state(self) -> RobotState:
        return RobotState(
            position=Position.from_list(self.robot.current_position),
            gripper=self.robot.gripper,
            moving=self.robot.moving,
        )

    def get_config(self) -> MachineConfig:
        return self.config

    def _cube_position(self) -> Position:
        if self._cube_location == CUBE_AT_TABLE_A:
            return self.config.cube_position
        if self._cube_location == CUBE_AT_TABLE_B:
            return self.config.destination_position
        return Position.from_list(self.robot.current_position)

    async def recent_events(self) -> EventList:
        return EventList(events=list(reversed(self._recent_events)))

    # ------------------------------------------------------------------
    # Persisted run state
    # ------------------------------------------------------------------

    def _restore_run_state(self) -> None:
        """Restore the last known gripper/run state and fail safe on interruption."""

        try:
            persisted = self.run_state_repository.load()
        except Exception:
            logger.exception("Could not load the persisted run state")
            persisted = None

        if persisted is None:
            self._save_run_state_safely("idle")
            return

        if persisted.robot_position.is_within_limits():
            try:
                self.robot.restore_position(persisted.robot_position.to_list())
            except Exception:
                logger.exception("Could not restore the persisted robot position")
        else:
            logger.warning(
                "Persisted robot position is outside the workspace; keeping home"
            )

        self._cube_location = persisted.cube_location or CUBE_AT_TABLE_A
        if persisted.gripper == "closed":
            self.robot.close_gripper()
        else:
            self.robot.open_gripper()

        if persisted.status in {"running", "interrupted"}:
            self._active_operation = persisted.operation
            self.machine.enter_fault(self._interrupted_message(persisted))
        elif persisted.status == "fault":
            self._active_operation = persisted.operation
            self.machine.enter_fault(
                persisted.fault or "The machine was in a fault state at shutdown."
            )
        else:
            self._active_operation = ""
            self._save_run_state_safely("idle")

    def _interrupted_message(self, persisted: RunState) -> str:
        position = persisted.robot_position
        operation = persisted.operation or "an operation"
        step = persisted.step or "an unknown step"
        return (
            f"The application shut down during {operation} at step '{step}'. "
            f"Last known position: X {position.x:g}, Y {position.y:g}, Z "
            f"{position.z:g}; gripper {persisted.gripper}. "
            "The robot has been stopped. Inspect the cell, then press Reset."
        )

    def _on_state_change(self, _old: str, new_state: str, _trigger: str) -> None:
        try:
            if new_state == "ready":
                self._active_operation = ""
                status = "idle"
            elif new_state == "fault":
                status = "fault"
            else:
                status = "running"
            self._save_run_state(status)
        except Exception:
            logger.exception("Could not persist the run state")

    def _on_gripper_change(self, state: str) -> None:
        try:
            if (
                state == "closed"
                and self.machine.state == "Cycle_closeGripper"
                and self._cube_location == CUBE_AT_TABLE_A
            ):
                self._cube_location = CUBE_HELD
                self._save_run_state("running")
            elif (
                state == "open"
                and self.machine.state == "Cycle_openGripper"
                and self._cube_location == CUBE_HELD
            ):
                self._cube_location = CUBE_AT_TABLE_B
                self._save_run_state("running")
        except Exception:
            logger.exception("Could not update the cube state")

    def _save_run_state(self, status: str) -> None:
        run_state = RunState(
            status=status,
            operation=self._active_operation,
            state=self.machine.state,
            step=self.machine.step,
            robot_position=Position.from_list(self.robot.current_position),
            gripper=self.robot.gripper,
            cube_location=self._cube_location,
            fault=self.machine.fault_message,
            updated_at=utc_now_iso(),
        )
        self.run_state_repository.save(run_state)
        self._last_position_save_at = time.monotonic()

    def persist_active_position(self) -> None:
        """Persist the moving robot position at most once per second."""

        if not self.machine.busy:
            return
        now = time.monotonic()
        if now - self._last_position_save_at < 1.0:
            return
        self._last_position_save_at = now
        self._save_run_state_safely("running")

    def _save_run_state_safely(self, status: str) -> None:
        try:
            self._save_run_state(status)
        except Exception:
            logger.exception("Could not persist the run state")

    async def shutdown(self) -> None:
        """Stop the robot and mark an in-progress operation as interrupted."""

        await self.machine.cancel_tasks()
        self.robot.halt()
        if self.machine.busy:
            self._save_run_state_safely("interrupted")
        elif self.machine.faulted:
            self._save_run_state_safely("fault")
        else:
            self._save_run_state_safely("idle")

    # ------------------------------------------------------------------
    # Events / telemetry
    # ------------------------------------------------------------------

    def make_event(self, level: str, message: str, detail: str = "") -> Event:
        self._event_id += 1
        event = Event(
            id=self._event_id,
            timestamp=utc_now_iso(),
            level=level,
            message=message,
            detail=detail,
        )
        self._recent_events.append(event)
        return event

    async def emit_event(self, level: str, message: str, detail: str = "") -> None:
        event = self.make_event(level, message, detail)
        await self.telemetry.publish_event(event)

    async def publish_status(self) -> None:
        await self.telemetry.publish_snapshot(self.status())

    async def _result(self, ok: bool, message: str) -> ActionResult:
        snapshot = self.status()
        await self.telemetry.publish_snapshot(snapshot)
        self.telemetry.wake()
        return ActionResult(ok=ok, message=message, status=snapshot)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def set_config(self, request: SetConfigRequest) -> ActionResult:
        async with self._lock:
            if self.machine.busy:
                return await self._result(
                    False, "Cannot change configuration while an operation is running"
                )
            try:
                config = request.to_config()
            except ValidationError as exc:
                return await self._result(False, validation_message(exc))
            except Exception as exc:  # noqa: BLE001 - report, do not crash the app
                return await self._result(False, str(exc) or "Invalid configuration")

            try:
                self.repository.save(config)
            except Exception as exc:  # noqa: BLE001 - persistence is best-effort
                logger.exception("Could not save configuration")
                return await self._result(False, f"Could not save configuration: {exc}")

            self.config = config
            await self.emit_event(
                "info",
                "Configuration saved",
                "Cube, destination, home, speed, and approach height updated.",
            )
            return await self._result(True, "Configuration saved")

    async def start_sequence(self) -> ActionResult:
        async with self._lock:
            if self.machine.faulted:
                return await self._result(False, "Reset the fault before starting the sequence")
            if self.machine.busy:
                return await self._result(False, "An operation is already running")
            if self.robot.moving:
                return await self._result(False, "The robot is still moving")
            if self._cube_location != CUBE_AT_TABLE_A:
                return await self._result(False, self._cube_start_message())
            if self.robot.gripper != "open":
                self.robot.open_gripper()
                await self.emit_event(
                    "info",
                    "Gripper opened",
                    "The gripper was opened before starting the sequence.",
                )
            self._active_operation = "sequence"
            if not self.machine.start_sequence(self.config):
                self._active_operation = ""
                self._save_run_state_safely("idle")
                return await self._result(False, f"Cannot start from state '{self.machine.state}'")
            await self.emit_event(
                "info",
                "Sequence started",
                "Picking from Table A and placing on Table B.",
            )
            return await self._result(True, "Sequence started")

    async def resume_sequence(self) -> ActionResult:
        async with self._lock:
            if self.machine.faulted:
                return await self._result(False, "Reset the fault before resuming the sequence")
            if self.machine.busy:
                return await self._result(False, "An operation is already running")
            if self.robot.moving:
                return await self._result(False, "The robot is still moving")
            if self._cube_location != CUBE_HELD:
                return await self._result(
                    False,
                    "Only a stopped sequence with the cube in the gripper can be resumed",
                )
            if self.robot.gripper != "closed":
                return await self._result(
                    False, "Close the gripper before resuming the sequence"
                )
            self._active_operation = "sequence"
            if not self.machine.resume_sequence(self.config):
                self._active_operation = ""
                self._save_run_state_safely("idle")
                return await self._result(
                    False, f"Cannot resume from state '{self.machine.state}'"
                )
            await self.emit_event(
                "info",
                "Sequence resumed",
                "Lifting the held cube, then moving it to Table B.",
            )
            return await self._result(True, "Sequence resumed")

    async def home_robot(self) -> ActionResult:
        async with self._lock:
            if self.machine.faulted:
                return await self._result(False, "Reset the fault before homing")
            if self.machine.busy:
                return await self._result(False, "An operation is already running")
            if self.robot.moving:
                return await self._result(False, "The robot is still moving")
            self._active_operation = "home"
            if not self.machine.home_robot(self.config):
                self._active_operation = ""
                self._save_run_state_safely("idle")
                return await self._result(False, f"Cannot home from state '{self.machine.state}'")
            await self.emit_event(
                "info",
                "Homing started",
                f"Moving to the configured home {self.config.home_position.to_list()}.",
            )
            return await self._result(True, "Homing started")

    async def move_robot(self, request: MoveRobotRequest) -> ActionResult:
        async with self._lock:
            if self.machine.faulted:
                return await self._result(False, "Reset the fault before moving")
            if self.machine.busy:
                return await self._result(False, "An operation is already running")
            if self.robot.moving:
                return await self._result(False, "The robot is still moving")

            position = request.position
            if not position.is_within_limits():
                return await self._result(
                    False, "Target position must be within +/-1000 mm on every axis"
                )
            self._active_operation = "position"
            if not self.machine.manual_move(position.to_list(), self.config.speed):
                self._active_operation = ""
                self._save_run_state_safely("idle")
                return await self._result(False, f"Cannot move from state '{self.machine.state}'")
            await self.emit_event(
                "info",
                "Position move started",
                f"Target position {position.to_list()}.",
            )
            return await self._result(True, "Position move started")

    def _cube_start_message(self) -> str:
        if self._cube_location == CUBE_AT_TABLE_B:
            return "The cube is on Table B. Reset it to Table A before starting"
        if self._cube_location == CUBE_HELD:
            return (
                "The sequence was stopped with the cube in the gripper. "
                "Resume it or reset the cube to Table A"
            )
        return "The cube location is unknown. Reset it to Table A before starting"

    async def reset_cube(self) -> ActionResult:
        async with self._lock:
            if self.machine.faulted:
                return await self._result(False, "Reset the fault before resetting the cube")
            if self.machine.busy or self.robot.moving:
                return await self._result(False, "Stop the robot before resetting the cube")
            if self.robot.gripper != "open":
                return await self._result(False, "Open the gripper before resetting the cube")
            self._cube_location = CUBE_AT_TABLE_A
            self._save_run_state_safely("idle")
            await self.emit_event(
                "info",
                "Cube reset to Table A",
                "Simulation reset of the cube position.",
            )
            return await self._result(True, "Cube reset to Table A")

    async def stop_sequence(self) -> ActionResult:
        async with self._lock:
            if self.machine.faulted:
                return await self._result(False, "Reset the fault instead of stopping")
            if not self.machine.busy:
                return await self._result(False, "No operation is running")

            await self.machine.cancel_tasks()
            self.robot.halt()
            self.machine.stop_operation()
            await self.emit_event(
                "warning",
                "Operation stopped",
                "The robot was halted at its current position.",
            )
            return await self._result(True, "Operation stopped")

    async def reset(self) -> ActionResult:
        async with self._lock:
            if not self.machine.faulted:
                return await self._result(False, "There is no fault to reset")

            await self.machine.cancel_tasks()
            self.robot.halt()
            self.machine.fault_message = ""
            if not self.machine.trigger("reset"):
                return await self._result(False, "Could not leave the fault state")
            await self.emit_event(
                "info",
                "Fault cleared",
                "The robot is ready for the next command.",
            )
            return await self._result(True, "Fault cleared")

    async def simulate_fault(self) -> ActionResult:
        async with self._lock:
            if not self.settings.enable_dev_tools:
                return await self._result(False, "Developer tools are disabled")
            if self.machine.faulted:
                return await self._result(False, "The machine is already in a fault state")

            await self.machine.cancel_tasks()
            self.robot.halt()
            message = "Simulated fault requested from the developer panel"
            if not self.machine.enter_fault(message):
                return await self._result(False, "Could not enter the fault state")
            await self.emit_event("error", "Simulated fault", message)
            return await self._result(True, "Fault simulated")
