"""Configuration persistence through vention-storage.

A single row (id=1) holds the whole machine configuration.  The repository
protocol lets the state machine/service tests run without SQLite, while the
SQLite implementation is exercised separately for real persistence.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from sqlmodel import Field, SQLModel
from storage.accessor import ModelAccessor

from app.models import DEFAULT_CONFIG, MachineConfig, Position, RunState, utc_now_iso

logger = logging.getLogger(__name__)


class ConfigRepository(Protocol):
    def load(self) -> MachineConfig: ...

    def save(self, config: MachineConfig) -> None: ...


class RunStateRepository(Protocol):
    def load(self) -> RunState | None: ...

    def save(self, run_state: RunState) -> None: ...


class ConfigRow(SQLModel, table=True):
    __tablename__ = "gantry_config"

    id: int = Field(default=1, primary_key=True)
    cube_x: float = 0.0
    cube_y: float = 0.0
    cube_z: float = 0.0
    destination_x: float = 0.0
    destination_y: float = 0.0
    destination_z: float = 0.0
    home_x: float = 0.0
    home_y: float = 0.0
    home_z: float = 0.0
    speed: int = 90
    approach_height: float = 100.0


def _row_to_config(row: ConfigRow) -> MachineConfig:
    from app.models import Position

    return MachineConfig(
        cube_position=Position(x=row.cube_x, y=row.cube_y, z=row.cube_z),
        destination_position=Position(
            x=row.destination_x, y=row.destination_y, z=row.destination_z
        ),
        home_position=Position(x=row.home_x, y=row.home_y, z=row.home_z),
        speed=row.speed,
        approach_height=row.approach_height,
    )


def _config_to_row(config: MachineConfig) -> ConfigRow:
    return ConfigRow(
        id=1,
        cube_x=config.cube_position.x,
        cube_y=config.cube_position.y,
        cube_z=config.cube_position.z,
        destination_x=config.destination_position.x,
        destination_y=config.destination_position.y,
        destination_z=config.destination_position.z,
        home_x=config.home_position.x,
        home_y=config.home_position.y,
        home_z=config.home_position.z,
        speed=config.speed,
        approach_height=config.approach_height,
    )


def ensure_sqlite_directory(database_url: str) -> None:
    """Create the parent directory for a file-backed SQLite URL."""

    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return
    raw_path = database_url[len(prefix) :]
    if not raw_path or raw_path == ":memory:":
        return
    Path(raw_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


class SqliteConfigRepository:
    """SQLite-backed repository using vention-storage's ModelAccessor."""

    def __init__(self, database_url: str) -> None:
        ensure_sqlite_directory(database_url)
        self.accessor: ModelAccessor[ConfigRow] = ModelAccessor(ConfigRow, "config")

    def load(self) -> MachineConfig:
        try:
            row = self.accessor.get(1)
        except Exception:
            logger.exception("Could not read the persisted configuration")
            return DEFAULT_CONFIG

        if row is None:
            try:
                self.save(DEFAULT_CONFIG)
            except Exception:
                logger.exception("Could not persist the default configuration")
            return DEFAULT_CONFIG

        try:
            return _row_to_config(row)
        except Exception as exc:
            logger.warning("Persisted configuration is invalid (%s); restoring defaults", exc)
            try:
                self.save(DEFAULT_CONFIG)
            except Exception:
                logger.exception("Could not restore the default configuration")
            return DEFAULT_CONFIG

    def save(self, config: MachineConfig) -> None:
        self.accessor.save(_config_to_row(config), actor="operator")


class InMemoryConfigRepository:
    """Test/development repository with the same semantics as the SQLite one."""

    def __init__(self, initial: MachineConfig = DEFAULT_CONFIG) -> None:
        self._config = initial
        self.saved: list[MachineConfig] = []

    def load(self) -> MachineConfig:
        return self._config

    def save(self, config: MachineConfig) -> None:
        self._config = config
        self.saved.append(config)


class RunStateRow(SQLModel, table=True):
    __tablename__ = "gantry_run_state"

    id: int = Field(default=1, primary_key=True)
    status: str = "idle"
    operation: str = ""
    state: str = "ready"
    step: str = "Ready"
    robot_x: float = 0.0
    robot_y: float = 0.0
    robot_z: float = 0.0
    gripper: str = "open"
    fault: str = ""
    updated_at: str = ""


def _row_to_run_state(row: RunStateRow) -> RunState:
    return RunState(
        status=row.status,
        operation=row.operation,
        state=row.state,
        step=row.step,
        robot_position=Position(x=row.robot_x, y=row.robot_y, z=row.robot_z),
        gripper=row.gripper,
        fault=row.fault,
        updated_at=row.updated_at or utc_now_iso(),
    )


def _run_state_to_row(run_state: RunState) -> RunStateRow:
    return RunStateRow(
        id=1,
        status=run_state.status,
        operation=run_state.operation,
        state=run_state.state,
        step=run_state.step,
        robot_x=run_state.robot_position.x,
        robot_y=run_state.robot_position.y,
        robot_z=run_state.robot_position.z,
        gripper=run_state.gripper,
        fault=run_state.fault,
        updated_at=run_state.updated_at,
    )


class SqliteRunStateRepository:
    """Persist the last operation/robot state alongside the configuration."""

    def __init__(self, database_url: str) -> None:
        ensure_sqlite_directory(database_url)
        self.accessor: ModelAccessor[RunStateRow] = ModelAccessor(RunStateRow, "run_state")

    def load(self) -> RunState | None:
        try:
            row = self.accessor.get(1)
        except Exception:
            logger.exception("Could not read the persisted run state")
            return None
        if row is None:
            return None
        try:
            return _row_to_run_state(row)
        except Exception:
            logger.exception("Persisted run state is invalid; ignoring it")
            return None

    def save(self, run_state: RunState) -> None:
        self.accessor.save(_run_state_to_row(run_state), actor="operator")


class InMemoryRunStateRepository:
    """Test/development repository for the run state."""

    def __init__(self, initial: RunState | None = None) -> None:
        self._run_state = initial
        self.saved: list[RunState] = []

    def load(self) -> RunState | None:
        return self._run_state

    def save(self, run_state: RunState) -> None:
        self._run_state = run_state
        self.saved.append(run_state)
