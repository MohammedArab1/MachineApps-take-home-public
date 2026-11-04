"""State-machine tests: sequence, faults, timeouts, cancellation, guards."""

from __future__ import annotations

import asyncio

import pytest

from app.machine import (
    CYCLE_PROGRESS,
    CYCLE_STATES,
    STEP_LABELS,
    PickAndPlaceMachine,
    States,
)
from app.models import DEFAULT_CONFIG, MachineConfig, Position
from tests.conftest import FakeRobot

EXPECTED_SEQUENCE = [
    ("move_to", [-750.0, 750.0, 100.0]),
    ("move_to", [-750.0, 750.0, 0.0]),
    ("close",),
    ("move_to", [-750.0, 750.0, 100.0]),
    ("move_to", [700.0, -700.0, 100.0]),
    ("move_to", [700.0, -700.0, 0.0]),
    ("open",),
    ("move_to", [700.0, -700.0, 100.0]),
]


def simplified(calls: list[tuple[object, ...]]) -> list[tuple[object, ...]]:
    result: list[tuple[object, ...]] = []
    for call in calls:
        if call[0] in ("move_to", "move_home"):
            result.append((call[0], call[1]))
        else:
            result.append((call[0],))
    return result


async def wait_done(machine: PickAndPlaceMachine, timeout: float = 2.0) -> None:
    await asyncio.wait_for(machine.operation_done.wait(), timeout)


async def wait_for_state(machine: PickAndPlaceMachine, state: str, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while machine.state != state:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"state {state!r} was not reached; current={machine.state!r}")
        await asyncio.sleep(0.001)


def test_state_names_are_hierarchical_and_parseable() -> None:
    assert str(States.cycle.moveToPick) == "Cycle_moveToPick"
    assert str(States.cycle.liftFromPlace) == "Cycle_liftFromPlace"
    assert str(States.homing.moveHome) == "Homing_moveHome"
    assert str(States.manual.move) == "Manual_move"
    # The hierarchy separator is "_"; member names must not contain it.
    for state in CYCLE_STATES:
        member = str(state).split("_", 1)[1]
        assert "_" not in member


async def test_happy_path_exact_sequence(
    machine: PickAndPlaceMachine, fake_robot: FakeRobot
) -> None:
    assert machine.start_sequence(DEFAULT_CONFIG)
    await wait_done(machine)

    assert machine.state == "ready"
    assert machine.step == "Ready"
    assert machine.progress == 1.0
    assert machine.fault_message == ""
    assert simplified(fake_robot.calls) == EXPECTED_SEQUENCE
    assert fake_robot.gripper == "open"
    assert fake_robot.current_position == [700.0, -700.0, 100.0]


async def test_move_to_is_called_repeatedly(
    machine: PickAndPlaceMachine, fake_robot: FakeRobot
) -> None:
    fake_robot.complete_after = 3
    assert machine.start_sequence(DEFAULT_CONFIG)
    await wait_done(machine)

    assert machine.state == "ready"
    # Six moves, each requiring three calls.
    assert len(fake_robot.move_calls) == 18


async def test_gripper_actions_happen_in_the_right_order(
    machine: PickAndPlaceMachine, fake_robot: FakeRobot
) -> None:
    assert machine.start_sequence(DEFAULT_CONFIG)
    await wait_done(machine)

    kinds = [call[0] for call in fake_robot.calls]
    close_index = kinds.index("close")
    open_index = kinds.index("open")
    move_indexes = [i for i, kind in enumerate(kinds) if kind == "move_to"]
    assert close_index < move_indexes[2]  # close before lifting from the pick
    assert open_index < move_indexes[5]  # open before lifting from the place


@pytest.mark.parametrize(
    ("fault_move", "expected_gripper"),
    [
        (1, "open"),
        (2, "open"),
        (3, "closed"),
        (4, "closed"),
        (5, "closed"),
        (6, "open"),
    ],
)
async def test_fault_at_each_move(fault_move: int, expected_gripper: str, fast_settings) -> None:
    robot = FakeRobot(fail_on_move=fault_move)
    machine = PickAndPlaceMachine(
        robot,
        poll_interval_s=fast_settings.poll_interval_s,
        gripper_settle_s=fast_settings.gripper_settle_s,
        min_motion_timeout_s=fast_settings.min_motion_timeout_s,
    )

    assert machine.start_sequence(DEFAULT_CONFIG)
    await wait_done(machine)

    assert machine.state == "fault"
    assert "simulated move failure" in machine.fault_message
    assert len(robot.move_calls) == fault_move
    assert robot.gripper == expected_gripper
    assert machine.operation_done.is_set()


async def test_fault_keeps_the_progress_of_the_failing_step(fast_settings) -> None:
    robot = FakeRobot(fail_on_move=3)  # liftFromPick is step 4/8
    machine = PickAndPlaceMachine(
        robot,
        poll_interval_s=fast_settings.poll_interval_s,
        gripper_settle_s=fast_settings.gripper_settle_s,
        min_motion_timeout_s=fast_settings.min_motion_timeout_s,
    )
    assert machine.start_sequence(DEFAULT_CONFIG)
    await wait_done(machine)
    assert machine.state == "fault"
    assert machine.progress == pytest.approx(4 / 8)


async def test_fault_on_close_gripper(fast_settings) -> None:
    robot = FakeRobot(fail_on_close=True)
    machine = PickAndPlaceMachine(
        robot,
        poll_interval_s=fast_settings.poll_interval_s,
        gripper_settle_s=fast_settings.gripper_settle_s,
        min_motion_timeout_s=fast_settings.min_motion_timeout_s,
    )
    assert machine.start_sequence(DEFAULT_CONFIG)
    await wait_done(machine)
    assert machine.state == "fault"
    assert "simulated gripper failure" in machine.fault_message


async def test_fault_on_open_gripper(fast_settings) -> None:
    robot = FakeRobot(fail_on_open=True)
    machine = PickAndPlaceMachine(
        robot,
        poll_interval_s=fast_settings.poll_interval_s,
        gripper_settle_s=fast_settings.gripper_settle_s,
        min_motion_timeout_s=fast_settings.min_motion_timeout_s,
    )
    assert machine.start_sequence(DEFAULT_CONFIG)
    await wait_done(machine)
    assert machine.state == "fault"
    assert "simulated gripper failure" in machine.fault_message


async def test_motion_timeout_faults(fast_settings) -> None:
    robot = FakeRobot(never_complete=True)
    machine = PickAndPlaceMachine(
        robot,
        poll_interval_s=0.001,
        gripper_settle_s=0.0,
        min_motion_timeout_s=0.05,
        motion_timeout_factor=0.0,
        motion_timeout_margin_s=0.0,
    )
    assert machine.start_sequence(DEFAULT_CONFIG)
    await wait_done(machine)
    assert machine.state == "fault"
    assert "timed out" in machine.fault_message
    assert robot.calls


async def test_stop_cancels_the_sequence_and_allows_a_restart(fast_settings) -> None:
    robot = FakeRobot(complete_after=100)
    machine = PickAndPlaceMachine(
        robot,
        poll_interval_s=0.001,
        gripper_settle_s=0.0,
        min_motion_timeout_s=0.2,
    )
    assert machine.start_sequence(DEFAULT_CONFIG)
    await wait_for_state(machine, "Cycle_moveToPick")
    await asyncio.sleep(0.005)
    assert robot.calls

    await machine.cancel_tasks()
    robot.halt()
    assert machine.stop_operation()
    assert machine.state == "ready"
    assert machine.step == "Ready"
    assert machine.progress == 0.0
    assert machine.operation_done.is_set()

    calls_after_stop = len(robot.calls)
    await asyncio.sleep(0.02)
    assert len(robot.calls) == calls_after_stop

    # A fresh sequence must re-plan and complete.
    robot.complete_after = 1
    robot._target = None  # noqa: SLF001 - deterministic test control
    robot._remaining = 1  # noqa: SLF001
    assert machine.start_sequence(DEFAULT_CONFIG)
    await wait_done(machine)
    assert machine.state == "ready"


async def test_home_uses_the_configured_home(fast_settings) -> None:
    robot = FakeRobot(position=[10.0, 20.0, 30.0])
    machine = PickAndPlaceMachine(
        robot,
        poll_interval_s=0.001,
        gripper_settle_s=0.0,
        min_motion_timeout_s=0.2,
    )
    config = MachineConfig(home_position=Position(x=0, y=0, z=0))
    assert machine.home_robot(config)
    await wait_done(machine)

    assert machine.state == "ready"
    assert machine.step == "Ready"
    assert machine.progress == 0.0
    assert ("move_home", [0.0, 0.0, 0.0], 90) in robot.calls
    assert robot.current_position == [0.0, 0.0, 0.0]


async def test_home_fault(fast_settings) -> None:
    robot = FakeRobot(position=[10.0, 20.0, 30.0], fail_on_home=True)
    machine = PickAndPlaceMachine(
        robot,
        poll_interval_s=0.001,
        gripper_settle_s=0.0,
        min_motion_timeout_s=0.2,
    )
    assert machine.home_robot(DEFAULT_CONFIG)
    await wait_done(machine)
    assert machine.state == "fault"
    assert "simulated home failure" in machine.fault_message


async def test_manual_move(fast_settings) -> None:
    robot = FakeRobot()
    machine = PickAndPlaceMachine(
        robot,
        poll_interval_s=0.001,
        gripper_settle_s=0.0,
        min_motion_timeout_s=0.2,
    )
    assert machine.manual_move([10.0, 20.0, 30.0], 50)
    await wait_done(machine)

    assert machine.state == "ready"
    assert machine.step == "Ready"
    assert robot.calls == [("move_to", [10.0, 20.0, 30.0], 50)]
    assert robot.current_position == [10.0, 20.0, 30.0]


async def test_busy_guards(fast_settings) -> None:
    robot = FakeRobot(complete_after=100)
    machine = PickAndPlaceMachine(
        robot,
        poll_interval_s=0.001,
        gripper_settle_s=0.0,
        min_motion_timeout_s=0.2,
    )
    assert machine.start_sequence(DEFAULT_CONFIG)
    await wait_for_state(machine, "Cycle_moveToPick")

    assert not machine.start_sequence(DEFAULT_CONFIG)
    assert not machine.home_robot(DEFAULT_CONFIG)
    assert not machine.manual_move([1.0, 2.0, 3.0], 50)

    await machine.cancel_tasks()
    robot.halt()
    assert machine.stop_operation()
    assert machine.state == "ready"


def test_guards_reject_missing_inputs(machine: PickAndPlaceMachine) -> None:
    assert not machine.trigger("start")
    assert not machine.trigger("home")
    assert not machine.trigger("manual")


def test_stop_from_ready_returns_false(machine: PickAndPlaceMachine) -> None:
    assert not machine.stop_operation()


def test_fault_from_ready_and_reset(machine: PickAndPlaceMachine) -> None:
    assert machine.enter_fault("developer test")
    assert machine.state == "fault"
    assert machine.fault_message == "developer test"
    assert machine.operation_done.is_set()
    assert not machine.enter_fault("again")
    assert machine.trigger("reset")
    assert machine.state == "ready"


def test_stop_and_fail_transitions_exist_for_every_active_state(
    machine: PickAndPlaceMachine,
) -> None:
    for state in CYCLE_STATES:
        name = str(state)
        triggers = machine.get_triggers(name)
        assert "stop" in triggers
        assert "fail" in triggers
    assert "stop" in machine.get_triggers("Homing_moveHome")
    assert "stop" in machine.get_triggers("Manual_move")
    assert "fail" in machine.get_triggers("ready")
    assert "reset" in machine.get_triggers("fault")


def test_progress_and_step_tables() -> None:
    assert CYCLE_PROGRESS["Cycle_moveToPick"] == pytest.approx(1 / 8)
    assert CYCLE_PROGRESS["Cycle_liftFromPlace"] == pytest.approx(1.0)
    assert STEP_LABELS["Cycle_moveToPick"] == "Moving to cube"
    assert STEP_LABELS["Cycle_lowerToPlace"] == "Lowering to destination"
    assert STEP_LABELS["Homing_moveHome"] == "Homing"
    assert STEP_LABELS["Manual_move"] == "Manual move"
    assert STEP_LABELS["ready"] == "Ready"
    assert STEP_LABELS["fault"] == "Fault"


async def test_operation_done_event_is_cleared_and_set(
    machine: PickAndPlaceMachine, fake_robot: FakeRobot
) -> None:
    fake_robot.complete_after = 100
    assert machine.operation_done.is_set()
    assert machine.start_sequence(DEFAULT_CONFIG)
    assert not machine.operation_done.is_set()
    await machine.cancel_tasks()
    fake_robot.halt()
    machine.stop_operation()
    assert machine.operation_done.is_set()


async def test_move_to_is_a_noop_when_already_there(
    machine: PickAndPlaceMachine, fake_robot: FakeRobot
) -> None:
    await machine._move_to([0.0, 0.0, 0.0], 90)  # noqa: SLF001
    assert fake_robot.calls == []


async def test_move_home_is_a_noop_when_already_there(
    machine: PickAndPlaceMachine, fake_robot: FakeRobot
) -> None:
    await machine._move_home([0.0, 0.0, 0.0], 90)  # noqa: SLF001
    assert fake_robot.calls == []


def test_require_config_raises(machine: PickAndPlaceMachine) -> None:
    with pytest.raises(RuntimeError, match="no operation configuration"):
        machine._require_config()  # noqa: SLF001


def test_manual_entry_without_target_faults(machine: PickAndPlaceMachine) -> None:
    machine._enter_manual(None)  # noqa: SLF001
    assert machine.state == "fault"
    assert "no manual target" in machine.fault_message


async def test_home_waits_for_motion_completion(
    fast_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    robot = FakeRobot(position=[10.0, 20.0, 30.0])
    machine = PickAndPlaceMachine(
        robot,
        poll_interval_s=0.001,
        gripper_settle_s=0.0,
        min_motion_timeout_s=0.2,
    )
    calls = {"count": 0}

    def slow_home(home: list[float], speed: int) -> None:
        calls["count"] += 1
        robot.calls.append(("move_home", list(home), speed))
        if calls["count"] < 2:
            robot.axis_speed = [1.0, 0.0, 0.0]
            return
        robot.position = list(home)
        robot.axis_speed = [0.0, 0.0, 0.0]

    monkeypatch.setattr(robot, "move_home", slow_home)
    assert machine.home_robot(DEFAULT_CONFIG)
    await wait_done(machine)

    assert machine.state == "ready"
    assert calls["count"] == 2


async def test_home_timeout_faults(fast_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    robot = FakeRobot(position=[10.0, 20.0, 30.0])
    machine = PickAndPlaceMachine(
        robot,
        poll_interval_s=0.001,
        gripper_settle_s=0.0,
        min_motion_timeout_s=0.05,
        motion_timeout_factor=0.0,
        motion_timeout_margin_s=0.0,
    )

    def never_home(home: list[float], speed: int) -> None:
        robot.calls.append(("move_home", list(home), speed))
        robot.axis_speed = [1.0, 0.0, 0.0]

    monkeypatch.setattr(robot, "move_home", never_home)
    assert machine.home_robot(DEFAULT_CONFIG)
    await wait_done(machine)

    assert machine.state == "fault"
    assert "timed out" in machine.fault_message


async def test_gripper_step_propagates_cancellation(
    machine: PickAndPlaceMachine,
) -> None:
    task = asyncio.create_task(
        machine._gripper_step(close=True, next_trigger="next")  # noqa: SLF001
    )
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
