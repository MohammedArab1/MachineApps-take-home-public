"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "gantry.db"
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://localhost:3000"


def _parse_origins(value: str) -> tuple[str, ...]:
    return tuple(origin.strip() for origin in value.split(",") if origin.strip())


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Runtime configuration.

    The timing values are deliberately injectable so tests can run the same
    production code without waiting for real motion.
    """

    db_url: str = f"sqlite:///{DEFAULT_DB_PATH}"
    cors_origins: tuple[str, ...] = _parse_origins(DEFAULT_CORS_ORIGINS)
    poll_interval_s: float = 0.02
    gripper_settle_s: float = 0.15
    status_idle_heartbeat_s: float = 1.0
    status_active_heartbeat_s: float = 0.1
    min_motion_timeout_s: float = 5.0
    motion_timeout_factor: float = 3.0
    motion_timeout_margin_s: float = 2.0
    enable_dev_tools: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        cors = _parse_origins(os.getenv("GANTRY_CORS_ORIGINS", DEFAULT_CORS_ORIGINS))
        return cls(
            db_url=os.getenv("GANTRY_DB_URL", f"sqlite:///{DEFAULT_DB_PATH}"),
            cors_origins=cors,
            poll_interval_s=float(os.getenv("GANTRY_POLL_INTERVAL_S", "0.02")),
            gripper_settle_s=float(os.getenv("GANTRY_GRIPPER_SETTLE_S", "0.15")),
            status_idle_heartbeat_s=float(os.getenv("GANTRY_STATUS_IDLE_HEARTBEAT_S", "1.0")),
            status_active_heartbeat_s=float(os.getenv("GANTRY_STATUS_ACTIVE_HEARTBEAT_S", "0.1")),
            min_motion_timeout_s=float(os.getenv("GANTRY_MIN_MOTION_TIMEOUT_S", "5.0")),
            motion_timeout_factor=float(os.getenv("GANTRY_MOTION_TIMEOUT_FACTOR", "3.0")),
            motion_timeout_margin_s=float(os.getenv("GANTRY_MOTION_TIMEOUT_MARGIN_S", "2.0")),
            enable_dev_tools=_as_bool(os.getenv("GANTRY_ENABLE_DEV_TOOLS"), True),
        )
