"""Persistence tests for the in-memory and SQLite repositories."""

from __future__ import annotations

from pathlib import Path

import pytest
import storage.database as database
from sqlmodel import SQLModel

from app.models import DEFAULT_CONFIG, MachineConfig, Position
from app.repository import (
    ConfigRow,
    InMemoryConfigRepository,
    SqliteConfigRepository,
    ensure_sqlite_directory,
)


def build_repo(tmp_path: Path) -> tuple[SqliteConfigRepository, str]:
    url = f"sqlite:///{tmp_path / 'gantry.db'}"
    database._ENGINE = None
    database._DATABASE_URL = url
    SQLModel.metadata.create_all(database.get_engine())
    return SqliteConfigRepository(url), url


def test_in_memory_round_trip() -> None:
    repository = InMemoryConfigRepository()
    assert repository.load() == DEFAULT_CONFIG

    custom = MachineConfig(
        cube_position=Position(x=-500, y=500, z=0),
        destination_position=Position(x=500, y=-500, z=0),
        home_position=Position(x=0, y=0, z=10),
        speed=50,
        approach_height=150,
    )
    repository.save(custom)

    assert repository.load() == custom
    assert repository.saved == [custom]


def test_sqlite_first_load_writes_defaults(tmp_path: Path, reset_storage_engine: None) -> None:
    repository, _ = build_repo(tmp_path)

    loaded = repository.load()

    assert loaded == DEFAULT_CONFIG
    row = repository.accessor.get(1)
    assert row is not None
    assert row.cube_x == -750
    assert row.speed == 90


def test_sqlite_round_trip_and_restart(tmp_path: Path, reset_storage_engine: None) -> None:
    repository, url = build_repo(tmp_path)
    repository.load()

    custom = MachineConfig(
        cube_position=Position(x=-600, y=600, z=0),
        destination_position=Position(x=600, y=-600, z=0),
        home_position=Position(x=10, y=20, z=30),
        speed=42,
        approach_height=120,
    )
    repository.save(custom)
    assert repository.load() == custom

    # Simulate a process restart: a new engine/repository against the same file.
    database._ENGINE = None
    database._DATABASE_URL = url
    restarted = SqliteConfigRepository(url)

    assert restarted.load() == custom


def test_invalid_persisted_row_falls_back_to_defaults(
    tmp_path: Path, reset_storage_engine: None
) -> None:
    repository, _ = build_repo(tmp_path)
    repository.load()

    repository.accessor.save(
        ConfigRow(
            id=1,
            cube_x=9999,
            cube_y=0,
            cube_z=0,
            destination_x=0,
            destination_y=0,
            destination_z=0,
            home_x=0,
            home_y=0,
            home_z=0,
            speed=90,
            approach_height=100,
        ),
        actor="test",
    )

    loaded = repository.load()

    assert loaded == DEFAULT_CONFIG
    row = repository.accessor.get(1)
    assert row is not None
    assert row.cube_x == -750


def test_load_returns_defaults_when_the_accessor_fails(
    tmp_path: Path, reset_storage_engine: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, _ = build_repo(tmp_path)

    def boom(_record_id: int) -> ConfigRow | None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(repository.accessor, "get", boom)

    assert repository.load() == DEFAULT_CONFIG


def test_ensure_sqlite_directory_creates_parents(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deeper" / "gantry.db"
    ensure_sqlite_directory(f"sqlite:///{target}")
    assert target.parent.is_dir()


def test_ensure_sqlite_directory_ignores_memory() -> None:
    ensure_sqlite_directory("sqlite:///:memory:")
    ensure_sqlite_directory("postgresql://localhost/db")


def test_default_save_failure_is_tolerated(
    tmp_path: Path, reset_storage_engine: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, _ = build_repo(tmp_path)

    def boom(_config) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(repository, "save", boom)

    assert repository.load() == DEFAULT_CONFIG


def test_invalid_row_restore_failure_is_tolerated(
    tmp_path: Path, reset_storage_engine: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, _ = build_repo(tmp_path)
    repository.accessor.save(
        ConfigRow(
            id=1,
            cube_x=9999,
            cube_y=0,
            cube_z=0,
            destination_x=0,
            destination_y=0,
            destination_z=0,
            home_x=0,
            home_y=0,
            home_z=0,
            speed=90,
            approach_height=100,
        ),
        actor="test",
    )

    def boom(_config) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(repository, "save", boom)

    assert repository.load() == DEFAULT_CONFIG
