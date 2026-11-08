"""Run-state persistence and safe restart tests."""

from __future__ import annotations

import asyncio

from app.machine import PickAndPlaceMachine
from app.models import (
    DEFAULT_CONFIG,
    MoveRobotRequest,
    Position,
    RunState,
)
from app.repository import InMemoryConfigRepository, InMemoryRunStateRepository
from app.service import GantryService
from tests.conftest import FakeRobot, FakeTelemetry


def build_machine(robot: FakeRobot, settings) -> PickAndPlaceMachine:
    return PickAndPlaceMachine(
        robot,
        poll_interval_s=settings.poll_interval_s,
        gripper_settle_s=settings.gripper_settle_s,
        min_motion_timeout_s=settings.min_motion_timeout_s,
        motion_timeout_factor=settings.motion_timeout_factor,
        motion_timeout_margin_s=settings.motion_timeout_margin_s,
    )


def build_service(
    robot: FakeRobot,
    machine: PickAndPlaceMachine,
    settings,
    run_state_repository: InMemoryRunStateRepository,
) -> GantryService:
    return GantryService(
        robot,
        machine,
        InMemoryConfigRepository(DEFAULT_CONFIG),
        settings,
        run_state_repository=run_state_repository,
        telemetry=FakeTelemetry(),
    )


async def wait_done(machine: PickAndPlaceMachine, timeout: float = 2.0) -> None:
    await asyncio.wait_for(machine.operation_done.wait(), timeout)


async def wait_for_state(machine: PickAndPlaceMachine, state: str, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while machine.state != state:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"state {state!r} was not reached; current={machine.state!r}")
        await asyncio.sleep(0.001)


def test_initial_run_state_is_idle(service: GantryService, run_state_repository) -> None:
    persisted = run_state_repository.load()
    assert persisted is not None
    assert persisted.status == "idle"
    assert persisted.state == "ready"
    assert persisted.gripper == "open"


async def test_start_sequence_persists_running_then_idle(
    service: GantryService, run_state_repository, fake_robot: FakeRobot
) -> None:
    fake_robot.complete_after = 100
    assert (await service.start_sequence()).ok
    await wait_for_state(service.machine, "Cycle_moveToPick")

    persisted = run_state_repository.load()
    assert persisted is not None
    assert persisted.status == "running"
    assert persisted.operation == "sequence"
    assert persisted.state == "Cycle_moveToPick"

    await service.stop_sequence()
    persisted = run_state_repository.load()
    assert persisted is not None
    assert persisted.status == "idle"
    assert persisted.operation == ""


async def test_active_position_is_persisted_periodically(
    service: GantryService,
    run_state_repository: InMemoryRunStateRepository,
    fake_robot: FakeRobot,
) -> None:
    fake_robot.complete_after = 100
    assert (await service.start_sequence()).ok
    await wait_for_state(service.machine, "Cycle_moveToPick")

    fake_robot.position = [12.0, 34.0, 56.0]
    saves_before = len(run_state_repository.saved)
    service._last_position_save_at = 0.0  # noqa: SLF001 - force the periodic save
    service.persist_active_position()

    assert len(run_state_repository.saved) == saves_before + 1
    persisted = run_state_repository.load()
    assert persisted is not None
    assert persisted.status == "running"
    assert persisted.robot_position == Position(x=12, y=34, z=56)

    service.persist_active_position()
    assert len(run_state_repository.saved) == saves_before + 1
    await service.stop_sequence()


async def test_shutdown_marks_interrupted_and_restart_faults(fast_settings) -> None:
    robot = FakeRobot(complete_after=100)
    machine = build_machine(robot, fast_settings)
    run_state_repository = InMemoryRunStateRepository()
    service = build_service(robot, machine, fast_settings, run_state_repository)

    assert (await service.start_sequence()).ok
    await wait_for_state(machine, "Cycle_moveToPick")
    await asyncio.sleep(0.005)

    await service.shutdown()

    assert robot.halt_count == 1
    assert robot.moving is False
    persisted = run_state_repository.load()
    assert persisted is not None
    assert persisted.status == "interrupted"
    assert persisted.operation == "sequence"
    assert persisted.state == "Cycle_moveToPick"

    restarted_robot = FakeRobot()
    restarted_machine = build_machine(restarted_robot, fast_settings)
    restarted = build_service(
        restarted_robot,
        restarted_machine,
        fast_settings,
        run_state_repository,
    )

    assert restarted.machine.state == "fault"
    assert "shut down during sequence" in restarted.machine.fault_message
    assert "Moving to cube" in restarted.machine.fault_message
    persisted = run_state_repository.load()
    assert persisted is not None
    assert persisted.status == "fault"

    result = await restarted.reset()
    assert result.ok
    assert restarted.machine.state == "ready"
    persisted = run_state_repository.load()
    assert persisted is not None
    assert persisted.status == "idle"


async def test_restart_from_idle_restores_position_and_gripper(fast_settings) -> None:
    run_state_repository = InMemoryRunStateRepository(
        RunState(
            status="idle",
            state="ready",
            step="Ready",
            robot_position=Position(x=123, y=-45, z=67),
            gripper="closed",
        )
    )
    robot = FakeRobot()
    machine = build_machine(robot, fast_settings)
    service = build_service(robot, machine, fast_settings, run_state_repository)

    assert service.machine.state == "ready"
    assert robot.current_position == [123.0, -45.0, 67.0]
    assert robot.gripper == "closed"


async def test_stop_then_restart_restores_position_and_can_resume(fast_settings) -> None:
    run_state_repository = InMemoryRunStateRepository()
    robot = FakeRobot(complete_after=100)
    machine = build_machine(robot, fast_settings)
    service = build_service(robot, machine, fast_settings, run_state_repository)

    assert (await service.start_sequence()).ok
    await wait_for_state(machine, "Cycle_liftFromPick")
    robot.position = [-500.0, 500.0, 60.0]
    assert (await service.stop_sequence()).ok

    persisted = run_state_repository.load()
    assert persisted is not None
    assert persisted.robot_position == Position(x=-500, y=500, z=60)
    assert persisted.cube_location == "held"
    assert persisted.gripper == "closed"

    restarted_robot = FakeRobot(complete_after=1)
    restarted_machine = build_machine(restarted_robot, fast_settings)
    restarted = build_service(
        restarted_robot,
        restarted_machine,
        fast_settings,
        run_state_repository,
    )

    assert restarted.machine.state == "ready"
    assert restarted_robot.current_position == [-500.0, 500.0, 60.0]
    assert restarted_robot.gripper == "closed"
    assert restarted.status().cube_location == "held"

    assert (await restarted.resume_sequence()).ok
    await wait_done(restarted.machine)
    assert restarted.status().cube_location == "table_b"


async def test_restart_from_fault_restores_fault(fast_settings) -> None:
    run_state_repository = InMemoryRunStateRepository(
        RunState(
            status="fault",
            operation="sequence",
            state="fault",
            step="Fault",
            fault="previous failure",
        )
    )
    robot = FakeRobot()
    machine = build_machine(robot, fast_settings)
    service = build_service(robot, machine, fast_settings, run_state_repository)

    assert service.machine.state == "fault"
    assert service.machine.fault_message == "previous failure"
    assert (await service.reset()).ok
    assert service.machine.state == "ready"


async def test_restart_from_interrupted_requires_reset(fast_settings) -> None:
    run_state_repository = InMemoryRunStateRepository(
        RunState(
            status="interrupted",
            operation="home",
            state="Homing_moveHome",
            step="Homing",
            robot_position=Position(x=10, y=20, z=30),
            gripper="open",
        )
    )
    robot = FakeRobot()
    machine = build_machine(robot, fast_settings)
    service = build_service(robot, machine, fast_settings, run_state_repository)

    assert service.machine.state == "fault"
    assert "shut down during home" in service.machine.fault_message
    assert "Homing" in service.machine.fault_message
    assert robot.current_position == [10.0, 20.0, 30.0]


async def test_gripper_state_survives_restart(fast_settings) -> None:
    run_state_repository = InMemoryRunStateRepository()
    robot = FakeRobot()
    machine = build_machine(robot, fast_settings)
    service = build_service(robot, machine, fast_settings, run_state_repository)

    robot.close_gripper()
    service._save_run_state_safely("idle")  # noqa: SLF001 - persist the stopped gripper
    persisted = run_state_repository.load()
    assert persisted is not None
    assert persisted.gripper == "closed"

    restarted_robot = FakeRobot()
    restarted_machine = build_machine(restarted_robot, fast_settings)
    build_service(
        restarted_robot,
        restarted_machine,
        fast_settings,
        run_state_repository,
    )

    assert restarted_robot.gripper == "closed"


async def test_shutdown_while_idle_saves_idle(service: GantryService, run_state_repository) -> None:
    await service.shutdown()
    persisted = run_state_repository.load()
    assert persisted is not None
    assert persisted.status == "idle"


async def test_shutdown_while_faulted_saves_fault(
    service: GantryService, run_state_repository
) -> None:
    assert (await service.simulate_fault()).ok
    await service.shutdown()
    persisted = run_state_repository.load()
    assert persisted is not None
    assert persisted.status == "fault"
    assert persisted.fault


class FailingRunStateRepository:
    def load(self) -> RunState | None:
        raise RuntimeError("run-state database unavailable")

    def save(self, run_state: RunState) -> None:
        raise RuntimeError("run-state database unavailable")


async def test_run_state_storage_failure_does_not_break_the_app(
    fast_settings,
) -> None:
    robot = FakeRobot()
    machine = build_machine(robot, fast_settings)
    service = GantryService(
        robot,
        machine,
        InMemoryConfigRepository(DEFAULT_CONFIG),
        fast_settings,
        run_state_repository=FailingRunStateRepository(),
        telemetry=FakeTelemetry(),
    )

    assert service.machine.state == "ready"
    assert (await service.start_sequence()).ok
    await wait_done(service.machine)
    assert service.machine.state == "ready"


async def test_motion_commands_require_a_stopped_robot(
    service: GantryService, fake_robot: FakeRobot
) -> None:
    fake_robot.axis_speed = [1.0, 0.0, 0.0]
    result = await service.move_robot(
        MoveRobotRequest(position=Position(x=10, y=0, z=0))
    )
    assert not result.ok
    assert not (await service.start_sequence()).ok
    assert not (await service.home_robot()).ok


async def test_start_sequence_opens_a_closed_gripper_at_table_a(
    service: GantryService, fake_robot: FakeRobot
) -> None:
    fake_robot.gripper = "closed"

    result = await service.start_sequence()

    assert result.ok
    assert fake_robot.calls[0] == ("open",)
    await wait_done(service.machine)
    assert service.machine.state == "ready"
    assert service.status().cube_location == "table_b"
