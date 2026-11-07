"""Pydantic models shared by the state machine, service, and RPC layer."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic.alias_generators import to_camel

ROBOT_LIMIT = 1000.0

CUBE_AT_TABLE_A = "table_a"
CUBE_HELD = "held"
CUBE_AT_TABLE_B = "table_b"
CUBE_UNKNOWN = "unknown"


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp with an explicit timezone."""

    return datetime.now(timezone.utc).isoformat()


def validation_message(exc: ValidationError) -> str:
    """Flatten a Pydantic ValidationError into a concise, human-readable string."""

    parts: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"] if part not in ("__root__",))
        message = error["msg"]
        parts.append(f"{location}: {message}" if location else message)
    return "; ".join(parts) or "Invalid configuration"


class Position(BaseModel):
    """A point in the robot's Cartesian frame, in millimetres."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        allow_inf_nan=False,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    @classmethod
    def from_list(cls, values: Sequence[float]) -> Position:
        if len(values) != 3:
            raise ValueError("a position requires exactly three coordinates")
        return cls(x=float(values[0]), y=float(values[1]), z=float(values[2]))

    def to_list(self) -> list[float]:
        return [self.x, self.y, self.z]

    def is_within_limits(self, limit: float = ROBOT_LIMIT) -> bool:
        return all(-limit <= value <= limit for value in self.to_list())


class MachineConfig(BaseModel):
    """The complete, validated machine configuration."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        allow_inf_nan=False,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    cube_position: Position = Field(default_factory=lambda: Position(x=-650.0, y=650.0, z=0.0))
    destination_position: Position = Field(
        default_factory=lambda: Position(x=630.0, y=-550.0, z=0.0)
    )
    home_position: Position = Field(default_factory=lambda: Position(x=0.0, y=0.0, z=0.0))
    speed: int = 90
    approach_height: float = 100.0

    @field_validator("speed")
    @classmethod
    def _validate_speed(cls, value: int) -> int:
        if not 1 <= value <= 100:
            raise ValueError("speed must be an integer between 1 and 100 mm/s")
        return value

    @field_validator("approach_height")
    @classmethod
    def _validate_approach_height(cls, value: float) -> float:
        if not 0 <= value <= ROBOT_LIMIT:
            raise ValueError("approachHeight must be between 0 and 1000 mm")
        return value

    @model_validator(mode="after")
    def _validate_positions(self) -> MachineConfig:
        for name in ("cube_position", "destination_position", "home_position"):
            position: Position = getattr(self, name)
            if not position.is_within_limits():
                raise ValueError(f"{name} must be within +/-{ROBOT_LIMIT:g} mm on every axis")

        for name in ("cube_position", "destination_position"):
            position = getattr(self, name)
            if position.z < 0:
                raise ValueError(f"{name}.z must be >= 0 (the table surface)")
            if position.z + self.approach_height > ROBOT_LIMIT:
                raise ValueError(f"{name}.z + approachHeight must be <= {ROBOT_LIMIT:g} mm")
        return self


DEFAULT_CONFIG = MachineConfig()


class SetConfigRequest(BaseModel):
    """Permissive request body; the service validates it into MachineConfig.

    The defaults make the RPC router tolerant of a missing field, while the
    action still returns a structured error for values that fail validation.
    """

    model_config = ConfigDict(
        extra="ignore",
        allow_inf_nan=False,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    cube_position: Position = Field(default_factory=lambda: DEFAULT_CONFIG.cube_position)
    destination_position: Position = Field(
        default_factory=lambda: DEFAULT_CONFIG.destination_position
    )
    home_position: Position = Field(default_factory=lambda: DEFAULT_CONFIG.home_position)
    speed: int = DEFAULT_CONFIG.speed
    approach_height: float = DEFAULT_CONFIG.approach_height

    def to_config(self) -> MachineConfig:
        return MachineConfig(
            cube_position=self.cube_position,
            destination_position=self.destination_position,
            home_position=self.home_position,
            speed=self.speed,
            approach_height=self.approach_height,
        )


class MoveRobotRequest(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        allow_inf_nan=False,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    position: Position = Field(default_factory=Position)


class JogRobotRequest(BaseModel):
    """One relative manual move along a single axis."""

    model_config = ConfigDict(
        extra="ignore",
        allow_inf_nan=False,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    axis: str = "x"
    delta: float = 0.0


class RunState(BaseModel):
    """Small persisted record of the last operation and robot state."""

    model_config = ConfigDict(
        extra="ignore",
        alias_generator=to_camel,
        populate_by_name=True,
    )

    status: str = "idle"
    operation: str = ""
    state: str = "ready"
    step: str = "Ready"
    robot_position: Position = Field(default_factory=Position)
    gripper: str = "open"
    cube_location: str = CUBE_AT_TABLE_A
    fault: str = ""
    updated_at: str = Field(default_factory=utc_now_iso)


class RobotState(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        alias_generator=to_camel,
        populate_by_name=True,
    )

    position: Position = Field(default_factory=Position)
    gripper: str = "open"
    moving: bool = False


class StatusSnapshot(BaseModel):
    """Everything the dashboard needs for one telemetry frame."""

    model_config = ConfigDict(
        extra="ignore",
        alias_generator=to_camel,
        populate_by_name=True,
    )

    robot_position: Position = Field(default_factory=Position)
    gripper: str = "open"
    moving: bool = False
    busy: bool = False
    state: str = "ready"
    step: str = "Ready"
    fault: str = ""
    progress: float = 0.0
    cube_location: str = CUBE_AT_TABLE_A
    cube_position: Position = Field(default_factory=Position)
    config: MachineConfig = Field(default_factory=lambda: DEFAULT_CONFIG)
    limits: Position = Field(
        default_factory=lambda: Position(x=ROBOT_LIMIT, y=ROBOT_LIMIT, z=ROBOT_LIMIT)
    )
    updated_at: str = Field(default_factory=utc_now_iso)


class ActionResult(BaseModel):
    """Structured result for every command RPC."""

    model_config = ConfigDict(
        extra="ignore",
        alias_generator=to_camel,
        populate_by_name=True,
    )

    ok: bool = False
    message: str = ""
    status: StatusSnapshot = Field(default_factory=StatusSnapshot)


class Event(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: int = 0
    timestamp: str = ""
    level: str = "info"
    message: str = ""
    detail: str = ""


class EventList(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        alias_generator=to_camel,
        populate_by_name=True,
    )

    events: list[Event] = Field(default_factory=list)
