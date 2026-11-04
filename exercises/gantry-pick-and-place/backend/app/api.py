"""Connect RPC actions.

The handlers delegate to a single GantryService instance bound at startup.
Every command returns a structured ActionResult instead of raising, because
the pinned vention-communication router serializes exceptions into a 200
error envelope that the generated client cannot distinguish from a default
response.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from communication.decorators import action

from app.models import (
    ActionResult,
    EventList,
    MachineConfig,
    MoveRobotRequest,
    RobotState,
    SetConfigRequest,
    StatusSnapshot,
)
from app.service import GantryService

_service: GantryService | None = None


def bind(service: GantryService) -> None:
    global _service
    _service = service


def get_service() -> GantryService:
    if _service is None:
        raise RuntimeError("GantryService has not been bound")
    return _service


async def _safe_command(
    command: Callable[[], Awaitable[ActionResult]],
) -> ActionResult:
    service = get_service()
    try:
        return await command()
    except Exception as exc:  # noqa: BLE001 - never leak an opaque error envelope
        return ActionResult(
            ok=False,
            message=str(exc) or exc.__class__.__name__,
            status=service.status(),
        )


@action("GetStatus")
async def get_status() -> StatusSnapshot:
    return get_service().status()


@action("GetConfig")
async def get_config() -> MachineConfig:
    return get_service().config


@action("SetConfig")
async def set_config(request: SetConfigRequest) -> ActionResult:
    service = get_service()
    return await _safe_command(lambda: service.set_config(request))


@action("GetRobotPosition")
async def get_robot_position() -> RobotState:
    return get_service().robot_state()


@action("SetRobotPosition")
async def set_robot_position(request: MoveRobotRequest) -> ActionResult:
    service = get_service()
    return await _safe_command(lambda: service.move_robot(request))


@action("HomeRobot")
async def home_robot() -> ActionResult:
    service = get_service()
    return await _safe_command(service.home_robot)


@action("StartSequence")
async def start_sequence() -> ActionResult:
    service = get_service()
    return await _safe_command(service.start_sequence)


@action("StopSequence")
async def stop_sequence() -> ActionResult:
    service = get_service()
    return await _safe_command(service.stop_sequence)


@action("Reset")
async def reset() -> ActionResult:
    service = get_service()
    return await _safe_command(service.reset)


@action("RecentEvents")
async def recent_events() -> EventList:
    return await get_service().recent_events()


@action("SimulateFault")
async def simulate_fault() -> ActionResult:
    service = get_service()
    return await _safe_command(service.simulate_fault)
