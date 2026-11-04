"""Application wiring.

Importing this module emits ``backend/proto/app.proto``; the frontend's Buf
build consumes that committed file.  The app is a module-level singleton so
``uvicorn app.main:app`` works, and the lifespan starts/stops the telemetry
heartbeat and the machine tasks.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from communication.app import VentionApp
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from storage.bootstrap import bootstrap

from app import api
from app.config import Settings
from app.machine import PickAndPlaceMachine
from app.repository import SqliteConfigRepository
from app.robot import SimRobotDriver
from app.service import GantryService
from app.telemetry import Telemetry
from robot_sim import Robot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

settings = Settings.from_env()
runtime: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    service: GantryService = runtime["service"]
    telemetry: Telemetry = runtime["telemetry"]
    task = asyncio.create_task(telemetry.run(), name="gantry-telemetry")
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await service.machine.cancel_tasks()
        service.robot.halt()


repository = SqliteConfigRepository(settings.db_url)

app = VentionApp(
    name="GantryPickAndPlace",
    emit_proto=True,
    proto_path=str(Path(__file__).resolve().parent.parent / "proto" / "app.proto"),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

bootstrap(
    app,
    accessors=[repository.accessor],
    database_url=settings.db_url,
    create_tables=True,
    max_records_per_model=None,
    enable_db_router=False,
)

initial_config = repository.load()
robot = SimRobotDriver(
    Robot(
        initial_position=initial_config.home_position.to_list(),
        home_position=initial_config.home_position.to_list(),
    )
)
machine = PickAndPlaceMachine(
    robot,
    poll_interval_s=settings.poll_interval_s,
    gripper_settle_s=settings.gripper_settle_s,
    min_motion_timeout_s=settings.min_motion_timeout_s,
    motion_timeout_factor=settings.motion_timeout_factor,
    motion_timeout_margin_s=settings.motion_timeout_margin_s,
)
service = GantryService(robot, machine, repository, settings)
api.bind(service)
runtime["service"] = service
runtime["telemetry"] = service.telemetry


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.finalize()
