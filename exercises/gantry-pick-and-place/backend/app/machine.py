"""Pick-and-place state machine.

Design notes
------------
* ``transitions`` (the engine behind vention-state-machine) is synchronous.
  Entry callbacks therefore schedule async work with ``self.spawn`` instead of
  being async themselves.
* The pinned library's built-in ``to_fault`` transition has an async
  ``cancel_tasks`` before-hook that ``transitions`` never awaits.  We use a
  custom ``fail`` trigger instead and cancel tasks explicitly from the service.
* Hierarchical state names use ``_`` as a separator, so state member names are
  camelCase and contain no underscores.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from state_machine.core import BaseStates, StateMachine
from state_machine.decorators import guard, on_enter_state, on_state_change
from state_machine.defs import State, StateGroup, Trigger

from app.models import MachineConfig
from app.robot import MotionTimeout, RobotDriver

logger = logging.getLogger(__name__)


class Cycle(StateGroup):
    moveToPick: State = State()
    lowerToPick: State = State()
    closeGripper: State = State()
    liftFromPick: State = State()
    moveToPlace: State = State()
    lowerToPlace: State = State()
    openGripper: State = State()
    liftFromPlace: State = State()


class Recovery(StateGroup):
    moveToPlace: State = State()


class Homing(StateGroup):
    moveHome: State = State()


class Positioning(StateGroup):
    move: State = State()


class States:
    cycle = Cycle()
    recovery = Recovery()
    homing = Homing()
    positioning = Positioning()


class Triggers:
    start = Trigger("start")
    resume = Trigger("resume")
    home = Trigger("home")
    position = Trigger("position")
    next = Trigger("next")
    homed = Trigger("homed")
    positioned = Trigger("positioned")
    stop = Trigger("stop")
    fail = Trigger("fail")


CYCLE_STATES = [
    States.cycle.moveToPick,
    States.cycle.lowerToPick,
    States.cycle.closeGripper,
    States.cycle.liftFromPick,
    States.cycle.moveToPlace,
    States.cycle.lowerToPlace,
    States.cycle.openGripper,
    States.cycle.liftFromPlace,
]

ACTIVE_STATES = [
    *CYCLE_STATES,
    States.recovery.moveToPlace,
    States.homing.moveHome,
    States.positioning.move,
]

TRANSITIONS: list[dict[str, str]] = [
    Triggers.start.transition(BaseStates.READY.value, States.cycle.moveToPick),
    Triggers.resume.transition(BaseStates.READY.value, States.recovery.moveToPlace),
    Triggers.home.transition(BaseStates.READY.value, States.homing.moveHome),
    Triggers.position.transition(BaseStates.READY.value, States.positioning.move),
    Triggers.next.transition(States.recovery.moveToPlace, States.cycle.lowerToPlace),
    Triggers.next.transition(States.cycle.moveToPick, States.cycle.lowerToPick),
    Triggers.next.transition(States.cycle.lowerToPick, States.cycle.closeGripper),
    Triggers.next.transition(States.cycle.closeGripper, States.cycle.liftFromPick),
    Triggers.next.transition(States.cycle.liftFromPick, States.cycle.moveToPlace),
    Triggers.next.transition(States.cycle.moveToPlace, States.cycle.lowerToPlace),
    Triggers.next.transition(States.cycle.lowerToPlace, States.cycle.openGripper),
    Triggers.next.transition(States.cycle.openGripper, States.cycle.liftFromPlace),
    Triggers.next.transition(States.cycle.liftFromPlace, BaseStates.READY.value),
    Triggers.homed.transition(States.homing.moveHome, BaseStates.READY.value),
    Triggers.positioned.transition(States.positioning.move, BaseStates.READY.value),
    Triggers.fail.transition(BaseStates.READY.value, BaseStates.FAULT.value),
]

for _state in ACTIVE_STATES:
    TRANSITIONS.append(Triggers.stop.transition(_state, BaseStates.READY.value))
    TRANSITIONS.append(Triggers.fail.transition(_state, BaseStates.FAULT.value))


STEP_LABELS: dict[str, str] = {
    str(States.cycle.moveToPick): "Moving to cube",
    str(States.cycle.lowerToPick): "Lowering to cube",
    str(States.cycle.closeGripper): "Closing gripper",
    str(States.cycle.liftFromPick): "Lifting cube",
    str(States.cycle.moveToPlace): "Moving to destination",
    str(States.cycle.lowerToPlace): "Lowering to destination",
    str(States.cycle.openGripper): "Opening gripper",
    str(States.cycle.liftFromPlace): "Lifting from destination",
    str(States.recovery.moveToPlace): "Resuming to destination",
    str(States.homing.moveHome): "Homing",
    str(States.positioning.move): "Moving to position",
    BaseStates.READY.value: "Ready",
    BaseStates.FAULT.value: "Fault",
}

CYCLE_PROGRESS: dict[str, float] = {
    str(state): (index + 1) / len(CYCLE_STATES) for index, state in enumerate(CYCLE_STATES)
}
CYCLE_PROGRESS[str(States.recovery.moveToPlace)] = CYCLE_PROGRESS[
    str(States.cycle.moveToPlace)
]


class PickAndPlaceMachine(StateMachine):
    """A small, explicit state machine for the pick-and-place cycle."""

    def __init__(
        self,
        robot: RobotDriver,
        *,
        poll_interval_s: float = 0.02,
        gripper_settle_s: float = 0.15,
        step_pause_s: float = 0.0,
        min_motion_timeout_s: float = 5.0,
        motion_timeout_factor: float = 3.0,
        motion_timeout_margin_s: float = 2.0,
    ) -> None:
        super().__init__(
            states=States,
            transitions=TRANSITIONS,
            enable_last_state_recovery=False,
            ignore_invalid_triggers=True,
        )
        self.robot = robot
        self.poll_interval_s = poll_interval_s
        self.gripper_settle_s = gripper_settle_s
        self.step_pause_s = step_pause_s
        self.min_motion_timeout_s = min_motion_timeout_s
        self.motion_timeout_factor = motion_timeout_factor
        self.motion_timeout_margin_s = motion_timeout_margin_s

        self.operation_config: MachineConfig | None = None
        self.position_target: list[float] | None = None
        self.position_speed: int = 90
        self.fault_message: str = ""
        self.step: str = "Ready"
        self.progress: float = 0.0
        self.operation_done = asyncio.Event()
        self.operation_done.set()
        # Optional synchronous hook used by the service to persist run state.
        self.state_listener: Callable[[str, str, str], None] | None = None
        # Optional hook called after a sequence gripper action succeeds.
        self.gripper_listener: Callable[[str], None] | None = None

    # ------------------------------------------------------------------
    # Public commands (the service calls these after its own checks)
    # ------------------------------------------------------------------

    def start_sequence(self, config: MachineConfig) -> bool:
        self.operation_config = config
        self.operation_done.clear()
        return bool(self.trigger(Triggers.start.name))

    def resume_sequence(self, config: MachineConfig) -> bool:
        self.operation_config = config
        self.operation_done.clear()
        return bool(self.trigger(Triggers.resume.name))

    def home_robot(self, config: MachineConfig) -> bool:
        self.operation_config = config
        self.operation_done.clear()
        return bool(self.trigger(Triggers.home.name))

    def position_move(self, target: list[float], speed: int) -> bool:
        self.position_target = list(target)
        self.position_speed = speed
        self.operation_done.clear()
        return bool(self.trigger(Triggers.position.name))

    def stop_operation(self) -> bool:
        return bool(self.trigger(Triggers.stop.name))

    def enter_fault(self, message: str) -> bool:
        self.fault_message = message
        return bool(self.trigger(Triggers.fail.name))

    # ------------------------------------------------------------------
    # Derived state
    # ------------------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self.state not in {BaseStates.READY.value, BaseStates.FAULT.value}

    @property
    def faulted(self) -> bool:
        return self.state == BaseStates.FAULT.value

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    @guard(Triggers.start)
    def _guard_start(self) -> bool:
        return self.state == BaseStates.READY.value and self.operation_config is not None

    @guard(Triggers.resume)
    def _guard_resume(self) -> bool:
        return self.state == BaseStates.READY.value and self.operation_config is not None

    @guard(Triggers.home)
    def _guard_home(self) -> bool:
        return self.state == BaseStates.READY.value and self.operation_config is not None

    @guard(Triggers.position)
    def _guard_position(self) -> bool:
        return self.state == BaseStates.READY.value and self.position_target is not None

    # ------------------------------------------------------------------
    # Global state bookkeeping
    # ------------------------------------------------------------------

    @on_state_change
    def _record_state(self, old_state: str, new_state: str, _trigger: str) -> None:
        self.step = STEP_LABELS.get(new_state, new_state)
        if new_state == BaseStates.READY.value:
            # A completed sequence shows 100%; stopping or homing shows 0%.
            self.progress = 1.0 if old_state == str(States.cycle.liftFromPlace) else 0.0
        elif new_state == BaseStates.FAULT.value:
            # Keep the progress of the step that faulted.
            pass
        else:
            self.progress = CYCLE_PROGRESS.get(new_state, 0.0)

        if new_state in {BaseStates.READY.value, BaseStates.FAULT.value}:
            self.operation_done.set()

        if self.state_listener is not None:
            try:
                self.state_listener(old_state, new_state, _trigger)
            except Exception:  # noqa: BLE001 - persistence must not break the machine
                logger.exception("State listener failed")

    # ------------------------------------------------------------------
    # Entry callbacks: synchronous, each schedules one async step task
    # ------------------------------------------------------------------

    @on_enter_state(States.cycle.moveToPick)
    def _enter_move_to_pick(self, _: Any) -> None:
        self._schedule_motion(self._pick_approach(), Triggers.next.name)

    @on_enter_state(States.cycle.lowerToPick)
    def _enter_lower_to_pick(self, _: Any) -> None:
        config = self._require_config()
        self._schedule_motion(config.cube_position.to_list(), Triggers.next.name)

    @on_enter_state(States.cycle.closeGripper)
    def _enter_close_gripper(self, _: Any) -> None:
        self.spawn(self._gripper_step(close=True, next_trigger=Triggers.next.name))

    @on_enter_state(States.cycle.liftFromPick)
    def _enter_lift_from_pick(self, _: Any) -> None:
        self._schedule_motion(self._pick_approach(), Triggers.next.name)

    @on_enter_state(States.cycle.moveToPlace)
    def _enter_move_to_place(self, _: Any) -> None:
        self._schedule_motion(self._place_approach(), Triggers.next.name)

    @on_enter_state(States.cycle.lowerToPlace)
    def _enter_lower_to_place(self, _: Any) -> None:
        config = self._require_config()
        self._schedule_motion(config.destination_position.to_list(), Triggers.next.name)

    @on_enter_state(States.cycle.openGripper)
    def _enter_open_gripper(self, _: Any) -> None:
        self.spawn(self._gripper_step(close=False, next_trigger=Triggers.next.name))

    @on_enter_state(States.cycle.liftFromPlace)
    def _enter_lift_from_place(self, _: Any) -> None:
        self._schedule_motion(self._place_approach(), Triggers.next.name)

    @on_enter_state(States.recovery.moveToPlace)
    def _enter_recovery_move_to_place(self, _: Any) -> None:
        self.spawn(self._resume_step(Triggers.next.name))

    @on_enter_state(States.homing.moveHome)
    def _enter_homing(self, _: Any) -> None:
        config = self._require_config()
        self.spawn(
            self._motion_step(
                config.home_position.to_list(),
                config.speed,
                Triggers.homed.name,
                home=True,
            )
        )

    @on_enter_state(States.positioning.move)
    def _enter_position(self, _: Any) -> None:
        if self.position_target is None:
            self._fail(RuntimeError("no position target was provided"))
            return
        self.spawn(
            self._motion_step(
                list(self.position_target),
                self.position_speed,
                Triggers.positioned.name,
            )
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_config(self) -> MachineConfig:
        if self.operation_config is None:
            raise RuntimeError("no operation configuration was provided")
        return self.operation_config

    def _pick_approach(self) -> list[float]:
        config = self._require_config()
        return [
            config.cube_position.x,
            config.cube_position.y,
            config.cube_position.z + config.approach_height,
        ]

    def _place_approach(self) -> list[float]:
        config = self._require_config()
        return [
            config.destination_position.x,
            config.destination_position.y,
            config.destination_position.z + config.approach_height,
        ]

    def _schedule_motion(self, target: list[float], next_trigger: str) -> None:
        config = self._require_config()
        self.spawn(self._motion_step(target, config.speed, next_trigger))

    def _timeout_for(self, target: list[float], speed: int) -> float:
        distance = max(
            abs(target[index] - self.robot.current_position[index]) for index in range(3)
        )
        expected = distance / max(speed, 1)
        return max(
            self.min_motion_timeout_s,
            expected * self.motion_timeout_factor + self.motion_timeout_margin_s,
        )

    async def _move_to(self, target: list[float], speed: int) -> None:
        loop = asyncio.get_running_loop()
        target = list(target)
        deadline = loop.time() + self._timeout_for(target, speed)
        while not self.robot.at(target) or self.robot.moving:
            if loop.time() > deadline:
                raise MotionTimeout(f"motion to {target} timed out")
            self.robot.move_to(target, speed)
            if self.robot.at(target) and not self.robot.moving:
                return
            await asyncio.sleep(self.poll_interval_s)

    async def _move_home(self, home: list[float], speed: int) -> None:
        loop = asyncio.get_running_loop()
        home = list(home)
        deadline = loop.time() + self._timeout_for(home, speed)
        while not self.robot.at(home) or self.robot.moving:
            if loop.time() > deadline:
                raise MotionTimeout(f"homing to {home} timed out")
            self.robot.move_home(home, speed)
            if self.robot.at(home) and not self.robot.moving:
                return
            await asyncio.sleep(self.poll_interval_s)

    async def _resume_step(self, next_trigger: str) -> None:
        """Lift the held cube clear, move to the place approach, then continue."""

        try:
            config = self._require_config()
            current = self.robot.current_position
            safe_z = max(
                current[2],
                config.cube_position.z + config.approach_height,
                config.destination_position.z + config.approach_height,
            )
            if abs(current[2] - safe_z) > 1e-9:
                await self._move_to([current[0], current[1], safe_z], config.speed)
            await self._move_to(self._place_approach(), config.speed)
            if self.step_pause_s > 0:
                await asyncio.sleep(self.step_pause_s)
            self.trigger(next_trigger)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - any step failure must fault
            self._fail(exc)

    async def _motion_step(
        self,
        target: list[float],
        speed: int,
        next_trigger: str,
        *,
        home: bool = False,
    ) -> None:
        try:
            if home:
                await self._move_home(target, speed)
            else:
                await self._move_to(target, speed)
            if self.step_pause_s > 0:
                await asyncio.sleep(self.step_pause_s)
            self.trigger(next_trigger)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - any step failure must fault
            self._fail(exc)

    async def _gripper_step(self, *, close: bool, next_trigger: str) -> None:
        try:
            if close:
                self.robot.close_gripper()
            else:
                self.robot.open_gripper()
            if self.gripper_listener is not None:
                try:
                    self.gripper_listener("closed" if close else "open")
                except Exception:  # noqa: BLE001 - cube bookkeeping must not break motion
                    logger.exception("Gripper listener failed")
            await asyncio.sleep(self.gripper_settle_s)
            if self.step_pause_s > 0:
                await asyncio.sleep(self.step_pause_s)
            self.trigger(next_trigger)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - any step failure must fault
            self._fail(exc)

    def _fail(self, exc: Exception) -> None:
        self.fault_message = str(exc) or exc.__class__.__name__
        logger.warning("Fault in %s: %s", self.state, self.fault_message)
        self.trigger(Triggers.fail.name)
