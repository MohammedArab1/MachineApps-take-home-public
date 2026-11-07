"""Proto emission sanity checks."""

from __future__ import annotations

from pathlib import Path

from communication.codegen import generate_proto

from app import main as main_module  # noqa: F401 - importing finalizes the app

PROTO_PATH = Path(__file__).resolve().parent.parent / "proto" / "app.proto"


def test_proto_file_is_in_sync_with_the_python_surface() -> None:
    assert PROTO_PATH.exists()
    assert PROTO_PATH.read_text(encoding="utf-8") == generate_proto("GantryPickAndPlace")


def test_proto_contains_the_expected_rpcs() -> None:
    proto = PROTO_PATH.read_text(encoding="utf-8")
    for rpc in (
        "GetStatus",
        "GetConfig",
        "SetConfig",
        "GetRobotPosition",
        "SetRobotPosition",
        "JogRobot",
        "OpenGripper",
        "CloseGripper",
        "ResetCube",
        "HomeRobot",
        "StartSequence",
        "ResumeSequence",
        "StopSequence",
        "Reset",
        "RecentEvents",
        "SimulateFault",
    ):
        assert f"rpc {rpc} (" in proto
    assert "rpc Status (google.protobuf.Empty) returns (stream StatusSnapshot);" in proto
    assert "rpc Events (google.protobuf.Empty) returns (stream Event);" in proto
