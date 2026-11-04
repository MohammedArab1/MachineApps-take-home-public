"""Validation and model tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import (
    DEFAULT_CONFIG,
    Event,
    EventList,
    MachineConfig,
    Position,
    SetConfigRequest,
    StatusSnapshot,
    validation_message,
)


def test_position_helpers() -> None:
    position = Position.from_list([1, 2, 3])
    assert position.to_list() == [1.0, 2.0, 3.0]
    assert position.is_within_limits()
    assert not Position(x=1001).is_within_limits()
    assert not Position(x=-1001).is_within_limits()
    assert Position(x=-1000, y=1000, z=0).is_within_limits()


def test_position_rejects_wrong_length() -> None:
    with pytest.raises(ValueError):
        Position.from_list([1, 2])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_position_rejects_non_finite(bad: float) -> None:
    with pytest.raises(ValidationError):
        Position(x=bad)


def test_default_config_is_valid() -> None:
    assert DEFAULT_CONFIG.cube_position == Position(x=-650, y=650, z=0)
    assert DEFAULT_CONFIG.destination_position == Position(x=630, y=-550, z=0)
    assert DEFAULT_CONFIG.home_position == Position(x=0, y=0, z=0)
    assert DEFAULT_CONFIG.speed == 90
    assert DEFAULT_CONFIG.approach_height == 100


@pytest.mark.parametrize("speed", [1, 50, 100])
def test_speed_boundaries_are_valid(speed: int) -> None:
    assert MachineConfig(speed=speed).speed == speed


@pytest.mark.parametrize("speed", [0, -1, 101])
def test_speed_out_of_range_is_invalid(speed: int) -> None:
    with pytest.raises(ValidationError):
        MachineConfig(speed=speed)


def test_speed_must_be_an_integer() -> None:
    with pytest.raises(ValidationError):
        MachineConfig(speed=90.5)


@pytest.mark.parametrize("height", [0, 100, 1000])
def test_approach_height_boundaries_are_valid(height: float) -> None:
    assert MachineConfig(approach_height=height).approach_height == height


@pytest.mark.parametrize("height", [-1, 1001])
def test_approach_height_out_of_range_is_invalid(height: float) -> None:
    with pytest.raises(ValidationError):
        MachineConfig(approach_height=height)


def test_positions_must_be_within_robot_limits() -> None:
    with pytest.raises(ValidationError):
        MachineConfig(cube_position=Position(x=1001))
    with pytest.raises(ValidationError):
        MachineConfig(destination_position=Position(y=-1001))
    with pytest.raises(ValidationError):
        MachineConfig(home_position=Position(z=1001))


def test_home_may_be_negative_but_tables_may_not() -> None:
    config = MachineConfig(home_position=Position(z=-1000))
    assert config.home_position.z == -1000
    with pytest.raises(ValidationError):
        MachineConfig(cube_position=Position(z=-1))
    with pytest.raises(ValidationError):
        MachineConfig(destination_position=Position(z=-1))


def test_approach_target_must_fit_in_the_workspace() -> None:
    with pytest.raises(ValidationError):
        MachineConfig(cube_position=Position(z=901), approach_height=100)
    # Exactly at the limit is allowed.
    config = MachineConfig(cube_position=Position(z=900), approach_height=100)
    assert config.cube_position.z + config.approach_height == 1000


def test_config_is_frozen() -> None:
    with pytest.raises(ValidationError):
        DEFAULT_CONFIG.speed = 50  # type: ignore[misc]


def test_config_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        MachineConfig(unknown=1)  # type: ignore[call-arg]


def test_set_config_request_defaults_match_defaults() -> None:
    assert SetConfigRequest().to_config() == DEFAULT_CONFIG


def test_set_config_request_validates_on_conversion() -> None:
    with pytest.raises(ValidationError):
        SetConfigRequest(speed=0).to_config()


def test_validation_message_is_readable() -> None:
    with pytest.raises(ValidationError) as captured:
        MachineConfig(speed=0)
    message = validation_message(captured.value)
    assert "speed" in message
    assert "between 1 and 100" in message


def test_status_snapshot_defaults() -> None:
    status = StatusSnapshot()
    assert status.state == "ready"
    assert status.step == "Ready"
    assert status.config == DEFAULT_CONFIG
    assert status.limits.to_list() == [1000.0, 1000.0, 1000.0]
    assert status.updated_at


def test_event_list_defaults() -> None:
    assert EventList().events == []
    event = Event(id=1, message="hello")
    assert EventList(events=[event]).events[0].message == "hello"
