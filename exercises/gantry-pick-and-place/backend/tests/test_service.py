"""Service-level tests: command rules, persistence failures, events."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from app.machine import PickAndPlaceMachine
from app.models import (
    DEFAULT_CONFIG,
    MachineConfig,
    MoveRobotRequest,
    Position,
    SetConfigRequest,
)
from app.repository import InMemoryConfigRepository, InMemoryRunStateRepository
from app.service import GantryService
from tests.conftest import FakeRobot, FakeTelemetry


async def wait_done(machine: PickAndPlaceMachine, timeout: float = 2.0) -> None:
    await asyncio.wait_for(machine.operation_done.wait(), timeout)


async def wait_for_state(machine: PickAndPlaceMachine, state: str, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while machine.state != state:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"state {state!r} was not reached; current={machine.state!r}")
        await asyncio.sleep(0.001)


class FailingRepository:
    def __init__(self, *, fail_load: bool = False) -> None:
        self.fail_load = fail_load
        self.saved: list[MachineConfig] = []

    def load(self) -> MachineConfig:
        if self.fail_load:
            raise RuntimeError("database unavailable")
        return DEFAULT_CONFIG

    def save(self, config: MachineConfig) -> None:
        raise RuntimeError("disk full")


def make_service(
    robot: FakeRobot,
    machine: PickAndPlaceMachine,
    settings,
    repository,
    telemetry: FakeTelemetry | None = None,
    run_state_repository: InMemoryRunStateRepository | None = None,
) -> GantryService:
    return GantryService(
        robot,
        machine,
        repository,
        settings,
        run_state_repository=run_state_repository or InMemoryRunStateRepository(),
        telemetry=telemetry or FakeTelemetry(),
    )


def test_initial_status(service: GantryService) -> None:
    status = service.status()
    assert status.state == "ready"
    assert status.step == "Ready"
    assert status.busy is False
    assert status.moving is False
    assert status.gripper == "open"
    assert status.config == DEFAULT_CONFIG
    assert status.limits.to_list() == [1000.0, 1000.0, 1000.0]
    assert status.fault == ""
    assert status.progress == 0.0


def test_get_config_and_robot_state(service: GantryService, fake_robot: FakeRobot) -> None:
    assert service.get_config() == DEFAULT_CONFIG
    fake_robot.position = [1.0, 2.0, 3.0]
    fake_robot.gripper = "closed"
    state = service.robot_state()
    assert state.position == Position(x=1, y=2, z=3)
    assert state.gripper == "closed"
    assert state.moving is False


async def test_set_config_valid(service: GantryService, fake_telemetry: FakeTelemetry) -> None:
    request = SetConfigRequest(
        cube_position=Position(x=-500, y=500, z=0),
        destination_position=Position(x=500, y=-500, z=0),
        home_position=Position(x=0, y=0, z=10),
        speed=50,
        approach_height=150,
    )
    result = await service.set_config(request)

    assert result.ok
    assert result.message == "Configuration saved"
    assert service.config.cube_position == Position(x=-500, y=500, z=0)
    assert service.config.speed == 50
    assert service.config.approach_height == 150
    assert service.repository.saved == [service.config]  # type: ignore[attr-defined]
    assert any(event.message == "Configuration saved" for event in fake_telemetry.events)
    assert fake_telemetry.snapshots


@pytest.mark.parametrize(
    "config_request",
    [
        SetConfigRequest(speed=0),
        SetConfigRequest(speed=101),
        SetConfigRequest(approach_height=-1),
        SetConfigRequest(cube_position=Position(x=1001)),
        SetConfigRequest(destination_position=Position(y=-1001)),
        SetConfigRequest(home_position=Position(z=1001)),
        SetConfigRequest(cube_position=Position(z=-1)),
        SetConfigRequest(cube_position=Position(z=950), approach_height=100),
    ],
)
async def test_set_config_invalid(
    service: GantryService,
    fake_telemetry: FakeTelemetry,
    config_request: SetConfigRequest,
) -> None:
    original = service.config
    result = await service.set_config(config_request)

    assert not result.ok
    assert result.message
    assert service.config == original
    assert service.repository.saved == []  # type: ignore[attr-defined]
    assert not fake_telemetry.events


async def test_set_config_rejected_while_busy(
    service: GantryService, fake_robot: FakeRobot
) -> None:
    fake_robot.complete_after = 100
    assert (await service.start_sequence()).ok
    await wait_for_state(service.machine, "Cycle_moveToPick")

    result = await service.set_config(SetConfigRequest(speed=50))

    assert not result.ok
    assert "running" in result.message
    await service.stop_sequence()


async def test_start_sequence_runs_to_completion(
    service: GantryService, fake_telemetry: FakeTelemetry
) -> None:
    result = await service.start_sequence()
    assert result.ok
    assert result.message == "Sequence started"
    assert result.status.state == "Cycle_moveToPick"

    await wait_done(service.machine)

    assert service.machine.state == "ready"
    assert service.status().progress == 1.0
    assert any(event.message == "Sequence started" for event in fake_telemetry.events)
    assert fake_telemetry.snapshots


async def test_double_start_is_serialized(service: GantryService, fake_robot: FakeRobot) -> None:
    fake_robot.complete_after = 100
    first, second = await asyncio.gather(service.start_sequence(), service.start_sequence())

    assert sorted([first.ok, second.ok]) == [False, True]
    rejected = first if not first.ok else second
    assert "already running" in rejected.message
    await service.stop_sequence()


async def test_start_is_rejected_in_fault(service: GantryService) -> None:
    assert (await service.simulate_fault()).ok
    result = await service.start_sequence()
    assert not result.ok
    assert "Reset" in result.message


async def test_home_robot(
    service: GantryService, fake_robot: FakeRobot, fake_telemetry: FakeTelemetry
) -> None:
    await service.set_config(SetConfigRequest(home_position=Position(x=10, y=20, z=30)))
    result = await service.home_robot()

    assert result.ok
    assert result.status.state == "Homing_moveHome"
    await wait_done(service.machine)
    assert service.machine.state == "ready"
    assert fake_robot.current_position == [10.0, 20.0, 30.0]
    assert any(event.message == "Homing started" for event in fake_telemetry.events)


async def test_move_robot(service: GantryService, fake_robot: FakeRobot) -> None:
    result = await service.move_robot(MoveRobotRequest(position=Position(x=10, y=20, z=30)))
    assert result.ok
    assert result.status.state == "Positioning_move"
    await wait_done(service.machine)
    assert service.machine.state == "ready"
    assert fake_robot.current_position == [10.0, 20.0, 30.0]


async def test_move_robot_rejects_out_of_limits(service: GantryService) -> None:
    result = await service.move_robot(MoveRobotRequest(position=Position(x=2000, y=0, z=0)))
    assert not result.ok
    assert "within" in result.message
    assert service.machine.state == "ready"


async def test_stop_sequence(
    service: GantryService, fake_robot: FakeRobot, fake_telemetry: FakeTelemetry
) -> None:
    fake_robot.complete_after = 100
    assert (await service.start_sequence()).ok
    await wait_for_state(service.machine, "Cycle_moveToPick")
    await asyncio.sleep(0.005)

    result = await service.stop_sequence()

    assert result.ok
    assert result.status.state == "ready"
    assert service.machine.state == "ready"
    assert fake_robot.halt_count == 1
    assert any(event.message == "Operation stopped" for event in fake_telemetry.events)

    calls_after_stop = len(fake_robot.calls)
    await asyncio.sleep(0.02)
    assert len(fake_robot.calls) == calls_after_stop


async def test_stop_sequence_when_idle(service: GantryService) -> None:
    result = await service.stop_sequence()
    assert not result.ok
    assert "No operation" in result.message


async def test_reset_after_fault(service: GantryService, fake_telemetry: FakeTelemetry) -> None:
    assert (await service.simulate_fault()).ok
    assert service.machine.state == "fault"

    result = await service.reset()

    assert result.ok
    assert result.status.state == "ready"
    assert service.machine.fault_message == ""
    assert any(event.message == "Fault cleared" for event in fake_telemetry.events)


async def test_reset_when_not_faulted(service: GantryService) -> None:
    result = await service.reset()
    assert not result.ok
    assert "no fault" in result.message.lower()


async def test_simulate_fault_is_rejected_when_already_faulted(
    service: GantryService,
) -> None:
    assert (await service.simulate_fault()).ok
    result = await service.simulate_fault()
    assert not result.ok
    assert "already" in result.message


async def test_simulate_fault_can_be_disabled(
    fake_robot: FakeRobot,
    machine: PickAndPlaceMachine,
    fast_settings,
) -> None:
    settings = replace(fast_settings, enable_dev_tools=False)
    service = make_service(fake_robot, machine, settings, InMemoryConfigRepository(DEFAULT_CONFIG))
    result = await service.simulate_fault()
    assert not result.ok
    assert "disabled" in result.message
    assert service.machine.state == "ready"


async def test_recent_events_are_newest_first(service: GantryService) -> None:
    await service.emit_event("info", "first")
    await service.emit_event("warning", "second")
    await service.emit_event("error", "third")

    events = (await service.recent_events()).events

    assert [event.message for event in events] == ["third", "second", "first"]
    assert [event.id for event in events] == [3, 2, 1]


async def test_repository_save_failure_keeps_config(
    fake_robot: FakeRobot, machine: PickAndPlaceMachine, fast_settings
) -> None:
    service = make_service(
        fake_robot,
        machine,
        fast_settings,
        FailingRepository(),
        FakeTelemetry(),
    )
    result = await service.set_config(SetConfigRequest(speed=50))

    assert not result.ok
    assert "Could not save" in result.message
    assert service.config == DEFAULT_CONFIG


def test_repository_load_failure_uses_defaults(
    fake_robot: FakeRobot, machine: PickAndPlaceMachine, fast_settings
) -> None:
    service = make_service(
        fake_robot,
        machine,
        fast_settings,
        FailingRepository(fail_load=True),
        FakeTelemetry(),
    )
    assert service.config == DEFAULT_CONFIG


async def test_status_reflects_robot_state(service: GantryService, fake_robot: FakeRobot) -> None:
    fake_robot.position = [1.0, 2.0, 3.0]
    fake_robot.gripper = "closed"
    fake_robot.axis_speed = [5.0, 0.0, 0.0]

    status = service.status()

    assert status.robot_position == Position(x=1, y=2, z=3)
    assert status.gripper == "closed"
    assert status.moving is True


async def test_events_have_increasing_ids_and_timestamps(
    service: GantryService,
) -> None:
    first = service.make_event("info", "a")
    second = service.make_event("info", "b")
    assert first.id == 1
    assert second.id == 2
    assert first.timestamp
    assert second.timestamp
