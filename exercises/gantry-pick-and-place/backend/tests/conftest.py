"""Shared test fixtures: deterministic fake robot, telemetry, and services."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

# Must be set before app.main is imported by any test module.
os.environ.setdefault(
    "GANTRY_DB_URL",
    f"sqlite:///{tempfile.mkdtemp(prefix='gantry-tests-')}/gantry-test.db",
)
os.environ.setdefault("GANTRY_ENABLE_DEV_TOOLS", "true")

import pytest

from app.config import Settings
from app.machine import PickAndPlaceMachine
from app.models import DEFAULT_CONFIG, Event, StatusSnapshot
from app.repository import InMemoryConfigRepository, InMemoryRunStateRepository
from app.robot import RobotError
from app.service import GantryService


class FakeTelemetry:
    """Records everything the service would publish."""

    def __init__(self) -> None:
        self.snapshots: list[StatusSnapshot] = []
        self.events: list[Event] = []
        self.wake_count = 0

    async def publish_snapshot(self, snapshot: StatusSnapshot) -> None:
        self.snapshots.append(snapshot)

    async def publish_event(self, event: Event) -> None:
        self.events.append(event)

    def wake(self) -> None:
        self.wake_count += 1


class FakeRobot:
    """A deterministic RobotDriver implementation.

    ``complete_after`` controls how many ``move_to`` calls a single target
    needs, which exercises the state machine's polling loop without sleeping
    on the real simulator's wall clock.
    """

    def __init__(
        self,
        position: list[float] | None = None,
        *,
        complete_after: int = 1,
        fail_on_call: int | None = None,
        fail_on_move: int | None = None,
        never_complete: bool = False,
        fail_on_close: bool = False,
        fail_on_open: bool = False,
        fail_on_home: bool = False,
    ) -> None:
        self.position = list(position or [0.0, 0.0, 0.0])
        self.gripper = "open"
        self.axis_speed = [0.0, 0.0, 0.0]
        self.calls: list[tuple[object, ...]] = []
        self.complete_after = complete_after
        self.fail_on_call = fail_on_call
        self.fail_on_move = fail_on_move
        self.never_complete = never_complete
        self.fail_on_close = fail_on_close
        self.fail_on_open = fail_on_open
        self.fail_on_home = fail_on_home
        self.halt_count = 0
        self._call_count = 0
        self._move_count = 0
        self._target: list[float] | None = None
        self._remaining = complete_after

    @property
    def current_position(self) -> list[float]:
        return list(self.position)

    @property
    def moving(self) -> bool:
        return any(abs(value) > 1e-9 for value in self.axis_speed)

    @property
    def limits(self) -> list[float]:
        return [1000.0, 1000.0, 1000.0]

    def at(self, target: list[float], tolerance: float = 1e-6) -> bool:
        return all(
            abs(current - wanted) <= tolerance
            for current, wanted in zip(self.position, target, strict=True)
        )

    def _record(self, *call: object) -> None:
        self.calls.append(call)
        self._call_count += 1
        if self.fail_on_call == self._call_count:
            raise RobotError("simulated move failure")

    def move_to(self, target: list[float], speed: int) -> None:
        target = list(target)
        self._record("move_to", target, speed)
        self._move_count += 1
        if self.fail_on_move == self._move_count:
            raise RobotError("simulated move failure")
        if self.never_complete:
            self.axis_speed = [1.0, 0.0, 0.0]
            return
        if target != self._target:
            self._target = target
            self._remaining = self.complete_after
        self._remaining -= 1
        if self._remaining <= 0:
            self.position = target
            self.axis_speed = [0.0, 0.0, 0.0]
        else:
            self.axis_speed = [1.0, 0.0, 0.0]

    def move_home(self, home: list[float], speed: int) -> None:
        self._record("move_home", list(home), speed)
        if self.fail_on_home:
            raise RobotError("simulated home failure")
        self.position = list(home)
        self.axis_speed = [0.0, 0.0, 0.0]

    def restore_position(self, position: list[float]) -> None:
        self.position = list(position)
        self.axis_speed = [0.0, 0.0, 0.0]
        self._target = None
        self._remaining = self.complete_after

    def close_gripper(self) -> None:
        self._record("close")
        if self.fail_on_close:
            raise RobotError("simulated gripper failure")
        self.gripper = "closed"

    def open_gripper(self) -> None:
        self._record("open")
        if self.fail_on_open:
            raise RobotError("simulated gripper failure")
        self.gripper = "open"

    def halt(self) -> None:
        self.halt_count += 1
        self.axis_speed = [0.0, 0.0, 0.0]
        self.calls.append(("halt",))

    @property
    def move_calls(self) -> list[list[float]]:
        return [call[1] for call in self.calls if call[0] == "move_to"]


@pytest.fixture
def fast_settings() -> Settings:
    return Settings(
        db_url="sqlite:///:memory:",
        poll_interval_s=0.001,
        gripper_settle_s=0.0,
        status_idle_heartbeat_s=0.01,
        status_active_heartbeat_s=0.01,
        min_motion_timeout_s=0.2,
        motion_timeout_factor=1.0,
        motion_timeout_margin_s=0.1,
        enable_dev_tools=True,
    )


@pytest.fixture
def fake_robot() -> FakeRobot:
    return FakeRobot()


@pytest.fixture
def machine(fake_robot: FakeRobot, fast_settings: Settings) -> PickAndPlaceMachine:
    return PickAndPlaceMachine(
        fake_robot,
        poll_interval_s=fast_settings.poll_interval_s,
        gripper_settle_s=fast_settings.gripper_settle_s,
        min_motion_timeout_s=fast_settings.min_motion_timeout_s,
        motion_timeout_factor=fast_settings.motion_timeout_factor,
        motion_timeout_margin_s=fast_settings.motion_timeout_margin_s,
    )


@pytest.fixture
def fake_telemetry() -> FakeTelemetry:
    return FakeTelemetry()


@pytest.fixture
def run_state_repository() -> InMemoryRunStateRepository:
    return InMemoryRunStateRepository()


@pytest.fixture
def service(
    fake_robot: FakeRobot,
    machine: PickAndPlaceMachine,
    fast_settings: Settings,
    fake_telemetry: FakeTelemetry,
    run_state_repository: InMemoryRunStateRepository,
) -> GantryService:
    repository = InMemoryConfigRepository(DEFAULT_CONFIG)
    return GantryService(
        fake_robot,
        machine,
        repository,
        fast_settings,
        run_state_repository=run_state_repository,
        telemetry=fake_telemetry,
    )


@pytest.fixture
def reset_storage_engine() -> Iterator[None]:
    """Restore vention-storage's global engine after a test that replaces it."""

    import storage.database as database

    old_engine = database._ENGINE
    old_url = database._DATABASE_URL
    database._ENGINE = None
    try:
        yield
    finally:
        database._ENGINE = old_engine
        database._DATABASE_URL = old_url
