"""Lifespan and app wiring tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import main as main_module


def test_lifespan_starts_telemetry_and_shuts_down_cleanly() -> None:
    with TestClient(main_module.app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        topic = main_module.app.connect_router.manager._topics["Status"]
        assert topic["last_value"] is not None
        assert topic["last_value"].state == "ready"

    # Exiting the context cancels the telemetry task and halts the robot.
    assert main_module.service.robot.moving is False
    run_state = main_module.service.run_state_repository.load()
    assert run_state is not None
    assert run_state.status == "idle"
