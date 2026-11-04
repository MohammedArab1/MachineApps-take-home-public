"""Robot driver abstraction over the provided ``robot_sim.Robot``.

The simulator advances motion only when ``move_to`` is called, so the state
machine repeatedly polls it.  This adapter centralizes the simulator's
quirks: speed validation, the zero-speed division bug, and the stale
``axis_speed`` left behind by an interrupted move.
"""

from __future__ import annotations

import time
from typing import Protocol

from robot_sim import GripperState, Robot

POSITION_TOLERANCE = 1e-6


class RobotError(RuntimeError):
    """Raised when the robot rejects or cannot complete a command."""


class MotionTimeout(RobotError):
    """Raised when a motion does not reach its target within the deadline."""


class RobotDriver(Protocol):
    @property
    def current_position(self) -> list[float]: ...

    @property
    def gripper(self) -> str: ...

    @property
    def moving(self) -> bool: ...

    @property
    def limits(self) -> list[float]: ...

    def at(self, target: list[float], tolerance: float = POSITION_TOLERANCE) -> bool: ...

    def move_to(self, target: list[float], speed: int) -> None: ...

    def move_home(self, home: list[float], speed: int) -> None: ...

    def close_gripper(self) -> None: ...

    def open_gripper(self) -> None: ...

    def halt(self) -> None: ...


class SimRobotDriver:
    """Concrete adapter around the exercise's ``Robot`` class."""

    def __init__(self, robot: Robot) -> None:
        self._robot = robot

    @property
    def current_position(self) -> list[float]:
        return list(self._robot.current_position)

    @property
    def gripper(self) -> str:
        return "open" if self._robot.gripper_state == GripperState.OPEN else "closed"

    @property
    def moving(self) -> bool:
        return any(abs(speed) > 1e-9 for speed in self._robot.axis_speed)

    @property
    def limits(self) -> list[float]:
        return list(self._robot.robot_limits)

    def at(self, target: list[float], tolerance: float = POSITION_TOLERANCE) -> bool:
        return all(
            abs(current - wanted) <= tolerance
            for current, wanted in zip(self.current_position, target, strict=True)
        )

    def _validate(self, target: list[float], speed: int) -> None:
        if len(target) != 3:
            raise RobotError("a target must contain exactly three coordinates")
        if not 1 <= speed <= 100:
            raise RobotError(f"speed {speed} is outside the allowed range 1..100 mm/s")
        for index, value in enumerate(target):
            limit = self._robot.robot_limits[index]
            if value > limit or value < -limit:
                raise RobotError(f"target axis {index} ({value}) is outside the limits +/-{limit}")

    def move_to(self, target: list[float], speed: int) -> None:
        self._validate(target, speed)
        _, _, error = self._robot.move_to(list(target), speed)
        if error:
            raise RobotError(error)

    def move_home(self, home: list[float], speed: int) -> None:
        self._validate(home, speed)
        self._robot.home_position = list(home)
        _, _, error = self._robot.move_home(speed)
        if error:
            raise RobotError(error)

    def close_gripper(self) -> None:
        self._robot.closed_gripper()

    def open_gripper(self) -> None:
        self._robot.open_gripper()

    def halt(self) -> None:
        """Stop advancing the simulator and force the next move to re-plan.

        ``robot_sim`` has no stop primitive: motion only advances when
        ``move_to`` is called.  Zeroing the axis speed prevents a later
        ``move_to`` from continuing with the interrupted move's velocity.
        """

        self._robot.axis_speed = [0.0, 0.0, 0.0]
        self._robot.last_motion_time = time.perf_counter()
