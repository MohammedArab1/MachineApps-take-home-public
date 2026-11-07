"""Cube-state model tests: the cube follows the sequence and can be reset."""

from __future__ import annotations

import asyncio

from app.machine import PickAndPlaceMachine
from app.models import DEFAULT_CONFIG, Position
from app.repository import InMemoryConfigRepository, InMemoryRunStateRepository
from app.service import GantryService
from tests.conftest import FakeRobot, FakeTelemetry


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


def build_machine(robot: FakeRobot, settings) -> PickAndPlaceMachine:
    return PickAndPlaceMachine(
        robot,
        poll_interval_s=settings.poll_interval_s,
        gripper_settle_s=0.5,
        min_motion_timeout_s=settings.min_motion_timeout_s,
        motion_timeout_factor=settings.motion_timeout_factor,
        motion_timeout_margin_s=settings.motion_timeout_margin_s,
    )


async def wait_for_state(machine: PickAndPlaceMachine, state: str, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while machine.state != state:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"state {state!r} was not reached; current={machine.state!r}")
        await asyncio.sleep(0.001)


async def wait_done(machine: PickAndPlaceMachine, timeout: float = 10.0) -> None:
    await asyncio.wait_for(machine.operation_done.wait(), timeout)


async def test_cube_follows_the_sequence_and_blocks_restart(fast_settings) -> None:
    robot = FakeRobot()
    machine = build_machine(robot, fast_settings)
    service = build_service(
        robot,
        machine,
        fast_settings,
        InMemoryRunStateRepository(),
    )

    assert service.status().cube_location == "table_a"
    assert service.status().cube_position == DEFAULT_CONFIG.cube_position

    assert (await service.start_sequence()).ok
    await wait_for_state(machine, "Cycle_closeGripper")
    assert service.status().cube_location == "held"

    await wait_done(machine)
    status = service.status()
    assert status.cube_location == "table_b"
    assert status.cube_position == DEFAULT_CONFIG.destination_position

    rejected = await service.start_sequence()
    assert not rejected.ok
    assert "Table B" in rejected.message

    assert (await service.reset_cube()).ok
    assert service.status().cube_location == "table_a"
    assert service.status().cube_position == DEFAULT_CONFIG.cube_position


async def test_reset_cube_requires_an_open_gripper(fast_settings) -> None:
    robot = FakeRobot()
    machine = build_machine(robot, fast_settings)
    service = build_service(
        robot,
        machine,
        fast_settings,
        InMemoryRunStateRepository(),
    )

    assert (await service.close_gripper()).ok
    rejected = await service.reset_cube()
    assert not rejected.ok
    assert "Open the gripper" in rejected.message

    assert (await service.open_gripper()).ok
    assert (await service.reset_cube()).ok
    assert service.status().cube_location == "table_a"


async def test_cube_state_survives_restart(fast_settings) -> None:
    robot = FakeRobot()
    machine = build_machine(robot, fast_settings)
    run_state_repository = InMemoryRunStateRepository()
    service = build_service(robot, machine, fast_settings, run_state_repository)

    assert (await service.start_sequence()).ok
    await wait_for_state(machine, "Cycle_closeGripper")
    assert service.status().cube_location == "held"

    # Simulate a crash: the last persisted state says the cube is held.
    await service.machine.cancel_tasks()
    service.robot.halt()
    service.machine.fault_message = "simulated interrupted run"
    service.machine.enter_fault("simulated interrupted run")
    service._save_run_state_safely("interrupted")

    restarted_robot = FakeRobot()
    restarted_machine = build_machine(restarted_robot, fast_settings)
    restarted = build_service(
        restarted_robot,
        restarted_machine,
        fast_settings,
        run_state_repository,
    )

    assert restarted.machine.state == "fault"
    assert restarted.status().cube_location == "held"
    assert restarted.status().cube_position == Position.from_list(restarted_robot.current_position)
