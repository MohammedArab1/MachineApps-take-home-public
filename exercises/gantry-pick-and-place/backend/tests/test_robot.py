"""Tests for the adapter around the provided robot_sim.Robot."""

from __future__ import annotations

import pytest

from app.robot import RobotError, SimRobotDriver
from robot_sim import GripperState, Robot


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def drive_until_done(
    driver: SimRobotDriver, target: list[float], speed: int, clock: FakeClock
) -> int:
    calls = 0
    while not driver.at(target) or driver.moving:
        driver.move_to(target, speed)
        calls += 1
        clock.now += 0.05
        assert calls < 1000, "the adapter never reached the target"
    return calls


def test_move_to_must_be_called_repeatedly(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    monkeypatch.setattr("robot_sim.time.perf_counter", clock)
    driver = SimRobotDriver(Robot(initial_position=[0, 0, 0]))

    calls = drive_until_done(driver, [10.0, 5.0, -3.0], 100, clock)

    assert calls > 1
    assert driver.at([10.0, 5.0, -3.0])
    assert not driver.moving


def test_move_home_uses_the_configured_home(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    monkeypatch.setattr("robot_sim.time.perf_counter", clock)
    driver = SimRobotDriver(Robot(initial_position=[10, 20, 30]))

    calls = 0
    home = [0.0, 0.0, 0.0]
    while not driver.at(home) or driver.moving:
        driver.move_home(home, 100)
        calls += 1
        clock.now += 0.05
        assert calls < 1000

    assert driver.at(home)


@pytest.mark.parametrize("speed", [0, -1, 101])
def test_invalid_speed_is_rejected_before_the_simulator(speed: int) -> None:
    robot = Robot()
    driver = SimRobotDriver(robot)
    with pytest.raises(RobotError, match="speed"):
        driver.move_to([1.0, 0.0, 0.0], speed)
    assert robot.axis_speed == [0, 0, 0]


def test_out_of_limits_target_is_rejected() -> None:
    driver = SimRobotDriver(Robot())
    with pytest.raises(RobotError, match="outside the limits"):
        driver.move_to([1001.0, 0.0, 0.0], 50)
    with pytest.raises(RobotError, match="outside the limits"):
        driver.move_to([0.0, -1001.0, 0.0], 50)


def test_wrong_target_length_is_rejected() -> None:
    driver = SimRobotDriver(Robot())
    with pytest.raises(RobotError, match="three coordinates"):
        driver.move_to([1.0, 2.0], 50)  # type: ignore[arg-type]


def test_halt_clears_stale_axis_speed_and_allows_replanning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    monkeypatch.setattr("robot_sim.time.perf_counter", clock)
    robot = Robot(initial_position=[0, 0, 0])
    driver = SimRobotDriver(robot)

    driver.move_to([100.0, 0.0, 0.0], 100)
    clock.now += 0.02
    driver.move_to([100.0, 0.0, 0.0], 100)
    assert robot.axis_speed != [0, 0, 0]

    driver.halt()
    assert robot.axis_speed == [0, 0, 0]

    # A new target must re-plan from the halted position, not continue the old move.
    calls = drive_until_done(driver, [0.0, 0.0, 0.0], 100, clock)
    assert calls > 1
    assert driver.at([0.0, 0.0, 0.0])


def test_gripper_mapping_and_commands() -> None:
    driver = SimRobotDriver(Robot())
    assert driver.gripper == "open"
    driver.close_gripper()
    assert driver.gripper == "closed"
    driver.open_gripper()
    assert driver.gripper == "open"


def test_position_is_returned_as_a_copy() -> None:
    driver = SimRobotDriver(Robot(initial_position=[1, 2, 3]))
    position = driver.current_position
    position.append(999)
    assert driver.current_position == [1.0, 2.0, 3.0]


def test_at_uses_a_tolerance() -> None:
    driver = SimRobotDriver(Robot(initial_position=[0, 0, 0]))
    assert driver.at([1e-7, 0, 0])
    assert not driver.at([1e-3, 0, 0])


def test_simulator_error_is_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    robot = Robot()
    driver = SimRobotDriver(robot)
    monkeypatch.setattr(
        robot,
        "move_to",
        lambda target, speed: ([0, 0, 0], [0, 0, 0], "simulated rejection"),
    )
    with pytest.raises(RobotError, match="simulated rejection"):
        driver.move_to([1.0, 0.0, 0.0], 50)


def test_limits_property() -> None:
    driver = SimRobotDriver(Robot())
    assert driver.limits == [1000, 1000, 1000]


def test_gripper_state_enum_is_understood() -> None:
    robot = Robot(gripper_state=GripperState.CLOSED)
    assert SimRobotDriver(robot).gripper == "closed"


def test_move_home_error_is_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    robot = Robot()
    driver = SimRobotDriver(robot)
    monkeypatch.setattr(
        robot,
        "move_home",
        lambda speed: ([0, 0, 0], [0, 0, 0], "home rejected"),
    )
    with pytest.raises(RobotError, match="home rejected"):
        driver.move_home([0.0, 0.0, 0.0], 50)
