"""Connect RPC integration tests through the real FastAPI/ASGI app."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app import api
from app import main as main_module
from app.machine import PickAndPlaceMachine
from app.models import DEFAULT_CONFIG
from app.repository import InMemoryConfigRepository, InMemoryRunStateRepository
from app.service import GantryService
from tests.conftest import FakeRobot, FakeTelemetry

SERVICE = "/rpc/vention.app.v1.GantryPickAndPlaceService"


@pytest.fixture
async def api_client(fast_settings):
    original = api.get_service()
    robot = FakeRobot()
    machine = PickAndPlaceMachine(
        robot,
        poll_interval_s=fast_settings.poll_interval_s,
        gripper_settle_s=fast_settings.gripper_settle_s,
        min_motion_timeout_s=fast_settings.min_motion_timeout_s,
        motion_timeout_factor=fast_settings.motion_timeout_factor,
        motion_timeout_margin_s=fast_settings.motion_timeout_margin_s,
    )
    service = GantryService(
        robot,
        machine,
        InMemoryConfigRepository(DEFAULT_CONFIG),
        fast_settings,
        run_state_repository=InMemoryRunStateRepository(),
        telemetry=FakeTelemetry(),
    )
    api.bind(service)
    transport = httpx.ASGITransport(app=main_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, service, robot
    api.bind(original)


async def post(client: httpx.AsyncClient, method: str, body: dict | None = None):
    return await client.post(f"{SERVICE}/{method}", json=body if body is not None else {})


async def wait_done(machine: PickAndPlaceMachine, timeout: float = 2.0) -> None:
    await asyncio.wait_for(machine.operation_done.wait(), timeout)


async def wait_for_state(machine: PickAndPlaceMachine, state: str, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while machine.state != state:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"state {state!r} was not reached; current={machine.state!r}")
        await asyncio.sleep(0.001)


async def test_health(api_client) -> None:
    client, _, _ = api_client
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_get_status_returns_camel_case_telemetry(api_client) -> None:
    client, service, _ = api_client
    response = await post(client, "GetStatus")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "ready"
    assert body["step"] == "Ready"
    assert body["gripper"] == "open"
    assert body["busy"] is False
    assert body["moving"] is False
    assert body["robotPosition"] == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert body["config"]["cubePosition"]["x"] == -650.0
    assert body["config"]["approachHeight"] == 100.0
    assert body["limits"] == {"x": 1000.0, "y": 1000.0, "z": 1000.0}
    assert body["updatedAt"]
    assert service.config == DEFAULT_CONFIG


async def test_get_config(api_client) -> None:
    client, _, _ = api_client
    response = await post(client, "GetConfig")

    assert response.status_code == 200
    body = response.json()
    assert body["cubePosition"] == {"x": -650.0, "y": 650.0, "z": 0.0}
    assert body["destinationPosition"] == {"x": 630.0, "y": -550.0, "z": 0.0}
    assert body["homePosition"] == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert body["speed"] == 90
    assert body["approachHeight"] == 100.0


async def test_set_config_persists_and_updates_status(api_client) -> None:
    client, service, _ = api_client
    body = {
        "cubePosition": {"x": -500, "y": 500, "z": 0},
        "destinationPosition": {"x": 500, "y": -500, "z": 0},
        "homePosition": {"x": 0, "y": 0, "z": 10},
        "speed": 50,
        "approachHeight": 150,
    }
    response = await post(client, "SetConfig", body)

    assert response.status_code == 200
    result = response.json()
    assert result["ok"] is True
    assert result["message"] == "Configuration saved"
    assert result["status"]["config"]["cubePosition"]["x"] == -500.0
    assert service.config.speed == 50

    config_response = await post(client, "GetConfig")
    assert config_response.json()["speed"] == 50
    assert config_response.json()["approachHeight"] == 150.0


async def test_set_config_invalid_returns_structured_error(api_client) -> None:
    client, service, _ = api_client
    response = await post(
        client,
        "SetConfig",
        {
            "cubePosition": {"x": -650, "y": 650, "z": 0},
            "destinationPosition": {"x": 630, "y": -550, "z": 0},
            "homePosition": {"x": 0, "y": 0, "z": 0},
            "speed": 0,
            "approachHeight": 100,
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["ok"] is False
    assert "speed" in result["message"]
    assert service.config == DEFAULT_CONFIG


async def test_get_robot_position(api_client) -> None:
    client, _, robot = api_client
    robot.position = [1.0, 2.0, 3.0]
    robot.gripper = "closed"

    response = await post(client, "GetRobotPosition")

    assert response.status_code == 200
    assert response.json() == {
        "position": {"x": 1.0, "y": 2.0, "z": 3.0},
        "gripper": "closed",
        "moving": False,
    }


async def test_set_robot_position_moves(api_client) -> None:
    client, service, robot = api_client
    response = await post(client, "SetRobotPosition", {"position": {"x": 10, "y": 20, "z": 30}})

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["status"]["state"] == "Manual_move"
    await wait_done(service.machine)
    assert robot.current_position == [10.0, 20.0, 30.0]

    position = await post(client, "GetRobotPosition")
    assert position.json()["position"] == {"x": 10.0, "y": 20.0, "z": 30.0}


async def test_set_robot_position_rejects_out_of_limits(api_client) -> None:
    client, service, _ = api_client
    response = await post(client, "SetRobotPosition", {"position": {"x": 2000, "y": 0, "z": 0}})

    assert response.status_code == 200
    result = response.json()
    assert result["ok"] is False
    assert "within" in result["message"]
    assert service.machine.state == "ready"


async def test_home_robot(api_client) -> None:
    client, service, robot = api_client
    await post(
        client,
        "SetConfig",
        {
            "cubePosition": {"x": -650, "y": 650, "z": 0},
            "destinationPosition": {"x": 630, "y": -550, "z": 0},
            "homePosition": {"x": 10, "y": 20, "z": 30},
            "speed": 90,
            "approachHeight": 100,
        },
    )

    response = await post(client, "HomeRobot")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["status"]["state"] == "Homing_moveHome"
    await wait_done(service.machine)
    assert robot.current_position == [10.0, 20.0, 30.0]


async def test_start_sequence_runs(api_client) -> None:
    client, service, robot = api_client
    response = await post(client, "StartSequence")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["status"]["state"] == "Cycle_moveToPick"
    await wait_done(service.machine)

    status = (await post(client, "GetStatus")).json()
    assert status["state"] == "ready"
    assert status["progress"] == 1.0
    assert robot.current_position == [630.0, -550.0, 100.0]


async def test_stop_sequence(api_client) -> None:
    client, service, robot = api_client
    robot.complete_after = 100
    await post(client, "StartSequence")
    await wait_for_state(service.machine, "Cycle_moveToPick")

    response = await post(client, "StopSequence")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["status"]["state"] == "ready"
    assert robot.halt_count == 1


async def test_resume_sequence_finishes_a_stopped_place(api_client) -> None:
    client, service, robot = api_client
    robot.complete_after = 100
    await post(client, "StartSequence")
    await wait_for_state(service.machine, "Cycle_liftFromPick")

    stop = await post(client, "StopSequence")
    assert stop.json()["ok"] is True
    stopped = (await post(client, "GetStatus")).json()
    assert stopped["cubeLocation"] == "held"
    assert stopped["gripper"] == "closed"

    start = await post(client, "StartSequence")
    assert start.json()["ok"] is False
    assert "Resume" in start.json()["message"]

    robot.complete_after = 1
    robot._target = None  # noqa: SLF001 - deterministic test control
    robot._remaining = 1  # noqa: SLF001
    response = await post(client, "ResumeSequence")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["status"]["state"] == "Recovery_moveToPlace"
    await wait_done(service.machine)

    final = (await post(client, "GetStatus")).json()
    assert final["state"] == "ready"
    assert final["cubeLocation"] == "table_b"
    assert robot.current_position == [630.0, -550.0, 100.0]


async def test_simulate_fault_and_reset(api_client) -> None:
    client, service, _ = api_client
    fault = await post(client, "SimulateFault")
    assert fault.json()["ok"] is True
    assert fault.json()["status"]["state"] == "fault"
    assert fault.json()["status"]["fault"]

    status = (await post(client, "GetStatus")).json()
    assert status["state"] == "fault"
    assert status["fault"]

    reset = await post(client, "Reset")
    assert reset.json()["ok"] is True
    assert reset.json()["status"]["state"] == "ready"
    assert service.machine.fault_message == ""


async def test_recent_events(api_client) -> None:
    client, _, _ = api_client
    await post(client, "SimulateFault")
    await post(client, "Reset")

    response = await post(client, "RecentEvents")

    assert response.status_code == 200
    events = response.json()["events"]
    assert events
    assert events[0]["message"] == "Fault cleared"
    assert events[0]["id"] > events[-1]["id"]


async def test_unknown_rpc_is_404(api_client) -> None:
    client, _, _ = api_client
    response = await post(client, "DoesNotExist")
    assert response.status_code == 404


def test_get_service_requires_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "_service", None)
    with pytest.raises(RuntimeError, match="not been bound"):
        api.get_service()


async def test_safe_command_catches_unexpected_errors() -> None:
    async def boom():
        raise RuntimeError("explode")

    result = await api._safe_command(boom)
    assert result.ok is False
    assert "explode" in result.message


async def test_start_sequence_opens_a_closed_gripper_at_table_a(api_client) -> None:
    client, service, robot = api_client
    robot.gripper = "closed"

    response = await post(client, "StartSequence")
    assert response.json()["ok"] is True

    await wait_done(service.machine)
    status = (await post(client, "GetStatus")).json()
    assert status["state"] == "ready"
    assert status["gripper"] == "open"
    assert status["cubeLocation"] == "table_b"
