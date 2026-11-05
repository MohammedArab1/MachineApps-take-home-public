"""Run-state persistence, safe restart, and manual control tests."""

from __future__ import annotations

import asyncio

from app.machine import PickAndPlaceMachine
from app.models import (
    DEFAULT_CONFIG,
    JogRobotRequest,
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


async def test_restart_from_idle_restores_gripper(fast_settings) -> None:
    run_state_repository = InMemoryRunStateRepository(
        RunState(
            status="idle",
            state="ready",
            step="Ready",
            gripper="closed",
        )
    )
    robot = FakeRobot()
    machine = build_machine(robot, fast_settings)
    service = build_service(robot, machine, fast_settings, run_state_repository)

    assert service.machine.state == "ready"
    assert robot.gripper == "closed"


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


async def test_jog_robot_moves_relative(service: GantryService, fake_robot: FakeRobot) -> None:
    result = await service.jog_robot(JogRobotRequest(axis="x", delta=50))
    assert result.ok
    assert result.status.state == "Manual_move"
    await wait_done(service.machine)
    assert fake_robot.current_position == [50.0, 0.0, 0.0]

    result = await service.jog_robot(JogRobotRequest(axis="z", delta=-10))
    assert result.ok
    await wait_done(service.machine)
    assert fake_robot.current_position == [50.0, 0.0, -10.0]


async def test_jog_robot_rejects_invalid_requests(
    service: GantryService, fake_robot: FakeRobot
) -> None:
    original = fake_robot.current_position

    assert not (await service.jog_robot(JogRobotRequest(axis="q", delta=10))).ok
    assert not (await service.jog_robot(JogRobotRequest(axis="x", delta=0))).ok
    assert not (
        await service.jog_robot(JogRobotRequest.model_construct(axis="x", delta=float("nan")))
    ).ok
    assert not (await service.jog_robot(JogRobotRequest(axis="x", delta=2000))).ok
    assert fake_robot.current_position == original
    assert service.machine.state == "ready"


async def test_jog_rejected_while_busy_and_in_fault(
    service: GantryService, fake_robot: FakeRobot
) -> None:
    fake_robot.complete_after = 100
    assert (await service.start_sequence()).ok
    await wait_for_state(service.machine, "Cycle_moveToPick")

    result = await service.jog_robot(JogRobotRequest(axis="x", delta=10))
    assert not result.ok
    assert "already running" in result.message
    await service.stop_sequence()

    assert (await service.simulate_fault()).ok
    result = await service.jog_robot(JogRobotRequest(axis="x", delta=10))
    assert not result.ok
    assert "Reset" in result.message
    assert (await service.reset()).ok


async def test_manual_gripper(service: GantryService, fake_robot: FakeRobot) -> None:
    result = await service.close_gripper()
    assert result.ok
    assert fake_robot.gripper == "closed"
    assert service.status().gripper == "closed"

    result = await service.close_gripper()
    assert result.ok
    assert "already closed" in result.message

    result = await service.open_gripper()
    assert result.ok
    assert fake_robot.gripper == "open"


async def test_manual_gripper_rejected_while_busy_and_in_fault(
    service: GantryService, fake_robot: FakeRobot
) -> None:
    fake_robot.complete_after = 100
    assert (await service.start_sequence()).ok
    await wait_for_state(service.machine, "Cycle_moveToPick")

    result = await service.close_gripper()
    assert not result.ok
    assert "Stop the robot" in result.message
    await service.stop_sequence()

    assert (await service.simulate_fault()).ok
    result = await service.close_gripper()
    assert not result.ok
    assert "Reset" in result.message
    assert (await service.reset()).ok


async def test_gripper_state_survives_restart(fast_settings) -> None:
    run_state_repository = InMemoryRunStateRepository()
    robot = FakeRobot()
    machine = build_machine(robot, fast_settings)
    service = build_service(robot, machine, fast_settings, run_state_repository)

    assert (await service.close_gripper()).ok
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


async def test_manual_commands_require_a_stopped_robot(
    service: GantryService, fake_robot: FakeRobot
) -> None:
    fake_robot.axis_speed = [1.0, 0.0, 0.0]
    assert not (await service.close_gripper()).ok
    assert not (await service.jog_robot(JogRobotRequest(axis="x", delta=10))).ok
    assert not (await service.start_sequence()).ok
    assert not (await service.home_robot()).ok
