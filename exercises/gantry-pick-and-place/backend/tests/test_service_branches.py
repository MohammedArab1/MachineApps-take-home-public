"""Targeted service branch tests: rejection paths and defensive catches."""

from __future__ import annotations

import asyncio

import pytest

from app.models import DEFAULT_CONFIG, MoveRobotRequest, SetConfigRequest
from app.service import GantryService
from tests.conftest import FakeRobot


async def wait_for_state(machine, state: str, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while machine.state != state:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"state {state!r} was not reached; current={machine.state!r}")
        await asyncio.sleep(0.001)


class BadConfigRequest:
    def to_config(self):
        raise RuntimeError("unexpected conversion failure")


async def test_set_config_unexpected_error_is_structured(
    service: GantryService,
) -> None:
    result = await service.set_config(BadConfigRequest())  # type: ignore[arg-type]
    assert not result.ok
    assert "unexpected conversion failure" in result.message


async def test_publish_status_directly(service: GantryService, fake_telemetry) -> None:
    await service.publish_status()
    assert len(fake_telemetry.snapshots) == 1
    assert fake_telemetry.snapshots[0].state == "ready"


async def test_start_rejected_by_machine(
    service: GantryService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service.machine, "start_sequence", lambda config: False)
    result = await service.start_sequence()
    assert not result.ok
    assert "Cannot start" in result.message


async def test_home_rejected_when_faulted(service: GantryService) -> None:
    assert (await service.simulate_fault()).ok
    result = await service.home_robot()
    assert not result.ok
    assert "Reset" in result.message


async def test_home_rejected_while_busy(service: GantryService, fake_robot: FakeRobot) -> None:
    fake_robot.complete_after = 100
    assert (await service.start_sequence()).ok
    await wait_for_state(service.machine, "Cycle_moveToPick")
    result = await service.home_robot()
    assert not result.ok
    assert "already running" in result.message
    await service.stop_sequence()


async def test_home_rejected_by_machine(
    service: GantryService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service.machine, "home_robot", lambda config: False)
    result = await service.home_robot()
    assert not result.ok
    assert "Cannot home" in result.message


async def test_move_rejected_when_faulted(service: GantryService) -> None:
    assert (await service.simulate_fault()).ok
    result = await service.move_robot(MoveRobotRequest())
    assert not result.ok
    assert "Reset" in result.message


async def test_move_rejected_while_busy(service: GantryService, fake_robot: FakeRobot) -> None:
    fake_robot.complete_after = 100
    assert (await service.start_sequence()).ok
    await wait_for_state(service.machine, "Cycle_moveToPick")
    result = await service.move_robot(MoveRobotRequest())
    assert not result.ok
    assert "already running" in result.message
    await service.stop_sequence()


async def test_move_rejected_by_machine(
    service: GantryService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service.machine, "position_move", lambda target, speed: False)
    result = await service.move_robot(MoveRobotRequest())
    assert not result.ok
    assert "Cannot move" in result.message


async def test_stop_rejected_when_faulted(service: GantryService) -> None:
    assert (await service.simulate_fault()).ok
    result = await service.stop_sequence()
    assert not result.ok
    assert "Reset" in result.message


async def test_reset_rejected_by_machine(
    service: GantryService, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (await service.simulate_fault()).ok
    monkeypatch.setattr(service.machine, "trigger", lambda *args, **kwargs: False)
    result = await service.reset()
    assert not result.ok
    assert "Could not leave" in result.message


async def test_simulate_fault_rejected_by_machine(
    service: GantryService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service.machine, "enter_fault", lambda message: False)
    result = await service.simulate_fault()
    assert not result.ok
    assert "Could not enter" in result.message


async def test_set_config_uses_defaults_when_fields_are_missing(
    service: GantryService,
) -> None:
    result = await service.set_config(SetConfigRequest())
    assert result.ok
    assert service.config == DEFAULT_CONFIG
