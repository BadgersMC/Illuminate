from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from illuminate.protocol import Operation, Response
from illuminate.server.projects import ProjectConfig, ProjectRegistry
from illuminate.server.sessions import SessionDirtyError, SessionError, SessionManager


class FakeClient:
    def __init__(self) -> None:
        self.operations: list[Operation] = []
        self.closed = False

    def request(self, operation: Operation, payload=None) -> Response:
        self.operations.append(operation)
        return Response.success("fake", {"closed": True})

    def close(self) -> None:
        self.closed = True


class FakeProcess:
    def __init__(self, *, hung: bool = False, exit_code: int | None = None) -> None:
        self.hung = hung
        self.exit_code = exit_code
        self.terminate_called = False
        self.kill_called = False

    def poll(self):
        return self.exit_code

    def wait(self, timeout=None):
        if self.hung and not self.kill_called:
            raise subprocess.TimeoutExpired("fixture", timeout)
        self.exit_code = 0
        return 0

    def terminate(self):
        self.terminate_called = True

    def kill(self):
        self.kill_called = True
        self.hung = False


def _registry(tmp_path) -> ProjectRegistry:
    return ProjectRegistry(
        [
            ProjectConfig(
                project_id="fixture",
                python=sys.executable,
                module="fixture.workbench",
                cwd=tmp_path.resolve(),
                scene_ids=frozenset({"triangle"}),
                environment={"FIXTURE_MODE": "1"},
            )
        ]
    )


def _launchable_manager(tmp_path, process: FakeProcess | None = None):
    captured: dict[str, object] = {}
    fake_process = process or FakeProcess()

    def process_factory(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        ready_path = Path(kwargs["env"]["ILLUMINATE_READY_FILE"])
        ready_path.write_text(
            json.dumps({"version": 1, "host": "127.0.0.1", "port": 43123}),
            encoding="utf-8",
        )
        return fake_process

    client = FakeClient()

    def connector(address, token, timeout):
        captured["address"] = address
        captured["token"] = token
        captured["connect_timeout"] = timeout
        return client

    manager = SessionManager(
        _registry(tmp_path),
        process_factory=process_factory,
        bridge_connector=connector,
        startup_timeout=0.2,
        poll_interval=0.001,
        graceful_timeout=0.001,
        terminate_timeout=0.001,
    )
    return manager, fake_process, client, captured


def test_launch_uses_registered_command_not_request_command(tmp_path) -> None:
    manager, _process, _client, captured = _launchable_manager(tmp_path)
    run_dir = tmp_path / "run"

    session = manager.launch("fixture", "triangle", run_dir, visible=False)

    assert session.project_id == "fixture"
    assert session.scene_id == "triangle"
    assert session.launch_argv == (sys.executable, "-m", "fixture.workbench")
    assert "caller-command" not in session.launch_argv
    assert captured["kwargs"]["cwd"] == str(tmp_path.resolve())
    assert captured["kwargs"]["env"]["FIXTURE_MODE"] == "1"
    assert captured["kwargs"]["env"]["ILLUMINATE_VISIBLE"] == "0"
    assert not session.readiness_path.exists()
    artifact_text = "".join(
        path.read_text(encoding="utf-8") for path in run_dir.rglob("*.json")
    )
    assert captured["token"] not in artifact_text
    manager.close(session.session_id, discard_unapplied=True)


def test_close_escalates_after_bounded_grace_period(tmp_path) -> None:
    manager, process, client, _captured = _launchable_manager(
        tmp_path, FakeProcess(hung=True)
    )
    session = manager.launch("fixture", "triangle", tmp_path / "run", visible=True)

    manager.close(session.session_id, discard_unapplied=True)

    assert client.operations == [Operation.CLOSE_SCENE]
    assert process.terminate_called
    assert process.kill_called
    assert client.closed


def test_dirty_close_requires_explicit_discard(tmp_path) -> None:
    manager, _process, _client, _captured = _launchable_manager(tmp_path)
    session = manager.launch("fixture", "triangle", tmp_path / "run", visible=True)
    session.mark_dirty(2)

    with pytest.raises(SessionDirtyError):
        manager.close(session.session_id, discard_unapplied=False)

    assert manager.require(session.session_id) is session
    manager.close(session.session_id, discard_unapplied=True)


def test_launch_fails_if_process_exits_before_readiness(tmp_path) -> None:
    process = FakeProcess(exit_code=7)

    def process_factory(argv, **kwargs):
        return process

    manager = SessionManager(
        _registry(tmp_path),
        process_factory=process_factory,
        startup_timeout=0.02,
        poll_interval=0.001,
    )

    with pytest.raises(SessionError, match="exited"):
        manager.launch("fixture", "triangle", tmp_path / "run", visible=False)


def test_launch_times_out_and_cleans_up_without_readiness(tmp_path) -> None:
    process = FakeProcess(hung=True)
    manager = SessionManager(
        _registry(tmp_path),
        process_factory=lambda argv, **kwargs: process,
        startup_timeout=0.005,
        poll_interval=0.001,
        graceful_timeout=0.001,
        terminate_timeout=0.001,
    )

    with pytest.raises(SessionError, match="timed out"):
        manager.launch("fixture", "triangle", tmp_path / "run", visible=False)

    assert process.terminate_called
    assert process.kill_called


def test_bad_bridge_handshake_is_reported_and_process_is_cleaned_up(tmp_path) -> None:
    process = FakeProcess(hung=True)

    def process_factory(argv, **kwargs):
        Path(kwargs["env"]["ILLUMINATE_READY_FILE"]).write_text(
            json.dumps({"version": 1, "host": "127.0.0.1", "port": 43123}),
            encoding="utf-8",
        )
        return process

    def rejected_connector(address, token, timeout):
        raise ConnectionError("authentication failed")

    manager = SessionManager(
        _registry(tmp_path),
        process_factory=process_factory,
        bridge_connector=rejected_connector,
        startup_timeout=0.02,
        poll_interval=0.001,
        terminate_timeout=0.001,
    )

    with pytest.raises(SessionError, match="bridge connection failed"):
        manager.launch("fixture", "triangle", tmp_path / "run", visible=False)

    assert process.terminate_called
    assert process.kill_called
