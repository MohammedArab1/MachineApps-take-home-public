"""Business orchestration: command serialization, validation, and status."""

from __future__ import annotations

import asyncio
import logging
from collections import deque

from pydantic import ValidationError

from app.config import Settings
from app.machine import PickAndPlaceMachine
from app.models import (
    DEFAULT_CONFIG,
    ActionResult,
    Event,
    EventList,
    MachineConfig,
    MoveRobotRequest,
    Position,
    RobotState,
    SetConfigRequest,
    StatusSnapshot,
    utc_now_iso,
    validation_message,
)
from app.repository import ConfigRepository
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
        telemetry: TelemetrySink | None = None,
    ) -> None:
        self.robot = robot
        self.machine = machine
        self.repository = repository
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

    async def recent_events(self) -> EventList:
        return EventList(events=list(reversed(self._recent_events)))

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
            if not self.machine.start_sequence(self.config):
                return await self._result(False, f"Cannot start from state '{self.machine.state}'")
            await self.emit_event(
                "info",
                "Sequence started",
                "Picking from Table A and placing on Table B.",
            )
            return await self._result(True, "Sequence started")

    async def home_robot(self) -> ActionResult:
        async with self._lock:
            if self.machine.faulted:
                return await self._result(False, "Reset the fault before homing")
            if self.machine.busy:
                return await self._result(False, "An operation is already running")
            if not self.machine.home_robot(self.config):
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

            position = request.position
            if not position.is_within_limits():
                return await self._result(
                    False, "Target position must be within +/-1000 mm on every axis"
                )
            if not self.machine.manual_move(position.to_list(), self.config.speed):
                return await self._result(False, f"Cannot move from state '{self.machine.state}'")
            await self.emit_event(
                "info",
                "Manual move started",
                f"Target position {position.to_list()}.",
            )
            return await self._result(True, "Manual move started")

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
