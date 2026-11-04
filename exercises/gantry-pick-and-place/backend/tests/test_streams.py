"""Stream tests: Connect framing, replay/latest policy, and a real server."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from communication.connect_router import _frame

from app import main as main_module
from app.models import Event, StatusSnapshot

BACKEND_DIR = Path(__file__).resolve().parent.parent
STATUS_URL = "/rpc/vention.app.v1.GantryPickAndPlaceService/Status"


async def test_status_stream_replays_and_keeps_latest() -> None:
    manager = main_module.app.connect_router.manager

    subscriber = manager.subscribe("Status")
    first = StatusSnapshot(state="ready")
    main_module.app.connect_router.publish("Status", first)
    assert await asyncio.wait_for(subscriber.queue.get(), 1) == first

    main_module.app.connect_router.publish("Status", StatusSnapshot(state="first"))
    main_module.app.connect_router.publish("Status", StatusSnapshot(state="latest"))
    await asyncio.sleep(0.02)
    latest = await asyncio.wait_for(subscriber.queue.get(), 1)
    assert latest.state == "latest"
    manager.unsubscribe("Status", subscriber)

    # replay=True: a new subscriber immediately receives the last value.
    replay_subscriber = manager.subscribe("Status")
    replayed = await asyncio.wait_for(replay_subscriber.queue.get(), 1)
    assert replayed.state == "latest"
    manager.unsubscribe("Status", replay_subscriber)


async def test_events_stream_does_not_replay() -> None:
    manager = main_module.app.connect_router.manager
    main_module.app.connect_router.publish("Events", Event(id=999, message="old"))
    await asyncio.sleep(0.02)

    subscriber = manager.subscribe("Events")
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(subscriber.queue.get(), 0.05)
    manager.unsubscribe("Events", subscriber)


def test_connect_frame_header() -> None:
    frame = _frame({"ok": True})
    assert frame[0] == 0x00
    length = int.from_bytes(frame[1:5], "big")
    assert length == len(frame) - 5
    assert json.loads(frame[5:]) == {"ok": True}

    trailer = _frame({"error": {"code": "internal"}}, trailer=True)
    assert trailer[0] == 0x80


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise AssertionError("the uvicorn test server did not become healthy")


def test_real_server_streams_connect_frames(tmp_path: Path) -> None:
    port = _free_port()
    env = os.environ.copy()
    env["GANTRY_DB_URL"] = f"sqlite:///{tmp_path / 'gantry.db'}"
    env["GANTRY_ENABLE_DEV_TOOLS"] = "false"
    env["GANTRY_STATUS_IDLE_HEARTBEAT_S"] = "0.05"

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=BACKEND_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_health(port)
        with (
            httpx.Client(timeout=5.0) as client,
            client.stream("POST", f"http://127.0.0.1:{port}{STATUS_URL}", json={}) as response,
        ):
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("application/connect+json")

            buffer = b""
            message: dict | None = None
            for chunk in response.iter_bytes():
                buffer += chunk
                while len(buffer) >= 5:
                    length = int.from_bytes(buffer[1:5], "big")
                    if len(buffer) < 5 + length:
                        break
                    body = buffer[5 : 5 + length]
                    buffer = buffer[5 + length :]
                    message = json.loads(body)
                    break
                if message is not None:
                    break

            assert message is not None
            assert message["state"] == "ready"
            assert "config" in message
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
