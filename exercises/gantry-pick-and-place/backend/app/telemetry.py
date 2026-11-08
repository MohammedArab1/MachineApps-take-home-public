"""Server streams and the telemetry heartbeat loop."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Protocol

from communication.decorators import stream

from app.models import Event, StatusSnapshot

if TYPE_CHECKING:
    from app.service import GantryService

logger = logging.getLogger(__name__)


@stream(
    name="Status",
    payload=StatusSnapshot,
    replay=True,
    queue_maxsize=1,
    policy="latest",
)
async def publish_status(snapshot: StatusSnapshot) -> StatusSnapshot:
    """Publish one status snapshot to every subscriber."""

    return snapshot


@stream(
    name="Events",
    payload=Event,
    replay=False,
    queue_maxsize=100,
    policy="fifo",
)
async def publish_event(event: Event) -> Event:
    """Publish one event to every subscriber."""

    return event


class TelemetrySink(Protocol):
    async def publish_snapshot(self, snapshot: StatusSnapshot) -> None: ...

    async def publish_event(self, event: Event) -> None: ...

    def wake(self) -> None: ...


class Telemetry:
    """Owns the status heartbeat and translates state changes into events."""

    def __init__(self, service: GantryService) -> None:
        self.service = service
        self._wake = asyncio.Event()
        self._last_state = service.machine.state

    def wake(self) -> None:
        """Ask the loop to publish immediately instead of waiting for its timeout."""

        self._wake.set()

    async def publish_snapshot(self, snapshot: StatusSnapshot) -> None:
        try:
            await publish_status(snapshot)
        except RuntimeError:
            # The stream publisher requires app.finalize(); unit tests may not have it.
            logger.debug("Status stream is not finalized yet")

    async def publish_event(self, event: Event) -> None:
        try:
            await publish_event(event)
        except RuntimeError:
            logger.debug("Event stream is not finalized yet")

    async def run(self) -> None:
        while True:
            state = self.service.machine.state
            if state != self._last_state:
                if state == "fault":
                    await self.service.emit_event(
                        "error", "Fault", self.service.machine.fault_message
                    )
                elif state == "ready" and self._last_state != "ready":
                    await self.service.emit_event(
                        "info", "Ready", f"Previous state: {self._last_state}"
                    )
                self._last_state = state

            await self.service.publish_status()
            self.service.persist_active_position()

            interval = (
                self.service.settings.status_active_heartbeat_s
                if self.service.machine.busy
                else self.service.settings.status_idle_heartbeat_s
            )
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=interval)
                self._wake.clear()
            except asyncio.TimeoutError:
                pass
