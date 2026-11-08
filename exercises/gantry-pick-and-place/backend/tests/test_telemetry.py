"""Telemetry heartbeat and stream-publishing tests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app import main as main_module
from app import telemetry as telemetry_module
from app.models import Event, StatusSnapshot
from app.telemetry import Telemetry


class FakeMachine:
    def __init__(self) -> None:
        self.state = "ready"
        self.busy = False
        self.fault_message = ""


class FakeService:
    def __init__(self) -> None:
        self.machine = FakeMachine()
        self.settings = SimpleNamespace(
            status_active_heartbeat_s=0.01,
            status_idle_heartbeat_s=0.01,
        )
        self.events: list[tuple[str, str, str]] = []
        self.status_count = 0
        self.position_saves = 0

    async def emit_event(self, level: str, message: str, detail: str = "") -> None:
        self.events.append((level, message, detail))

    async def publish_status(self) -> None:
        self.status_count += 1

    def persist_active_position(self) -> None:
        self.position_saves += 1


async def test_run_publishes_status_and_emits_state_events() -> None:
    service = FakeService()
    telemetry = Telemetry(service)  # type: ignore[arg-type]
    task = asyncio.create_task(telemetry.run())
    try:
        await asyncio.sleep(0.03)
        assert service.status_count >= 1
        assert service.position_saves >= 1

        service.machine.state = "fault"
        service.machine.fault_message = "boom"
        telemetry.wake()
        await asyncio.sleep(0.03)
        assert ("error", "Fault", "boom") in service.events

        service.machine.state = "ready"
        telemetry.wake()
        await asyncio.sleep(0.03)
        assert any(event[0] == "info" and event[1] == "Ready" for event in service.events)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_real_telemetry_publishes_to_connect_streams() -> None:
    telemetry = main_module.service.telemetry
    await telemetry.publish_snapshot(StatusSnapshot(state="telemetry-test"))
    await telemetry.publish_event(Event(id=42, message="telemetry-test"))


async def test_unfinalized_stream_errors_are_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    telemetry = main_module.service.telemetry

    async def boom(*args, **kwargs):
        raise RuntimeError("stream not finalized")

    monkeypatch.setattr(telemetry_module, "publish_status", boom)
    monkeypatch.setattr(telemetry_module, "publish_event", boom)

    await telemetry.publish_snapshot(StatusSnapshot())
    await telemetry.publish_event(Event())
