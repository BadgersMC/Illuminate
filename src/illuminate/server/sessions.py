"""Bounded ownership of launched Panda workbench processes."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
from typing import Callable, Mapping, Any
import uuid

from illuminate.bridge.transport import BridgeAddress
from illuminate.protocol import Operation

from .artifacts import RunArtifacts
from .client import BridgeClient
from .projects import ProjectRegistry


class SessionError(RuntimeError):
    pass


class SessionDirtyError(SessionError):
    pass


@dataclass
class Session:
    session_id: str
    project_id: str
    scene_id: str
    run_artifacts: RunArtifacts
    launch_argv: tuple[str, ...]
    readiness_path: Path
    process: Any = field(repr=False)
    client: Any = field(repr=False)
    revision: int = 0
    dirty: bool = False

    def mark_dirty(self, revision: int) -> None:
        if revision < 0:
            raise ValueError("revision must be non-negative")
        self.revision = revision
        self.dirty = True

    def mark_clean(self, revision: int) -> None:
        if revision < 0:
            raise ValueError("revision must be non-negative")
        self.revision = revision
        self.dirty = False


class SessionManager:
    def __init__(
        self,
        registry: ProjectRegistry,
        *,
        process_factory: Callable[..., Any] = subprocess.Popen,
        bridge_connector: Callable[..., Any] = BridgeClient.connect,
        startup_timeout: float = 10.0,
        poll_interval: float = 0.05,
        graceful_timeout: float = 2.0,
        terminate_timeout: float = 1.0,
    ) -> None:
        self._registry = registry
        self._process_factory = process_factory
        self._bridge_connector = bridge_connector
        self._startup_timeout = startup_timeout
        self._poll_interval = poll_interval
        self._graceful_timeout = graceful_timeout
        self._terminate_timeout = terminate_timeout
        self._sessions: dict[str, Session] = {}

    def launch(
        self,
        project_id: str,
        scene_id: str,
        run_dir: Path | str,
        visible: bool,
    ) -> Session:
        project = self._registry.require_scene(project_id, scene_id)
        token = secrets.token_urlsafe(32)
        artifacts = RunArtifacts(run_dir, secrets={token})
        ready_path = artifacts.path(".bridge-ready.json")
        argv = (project.python, "-m", project.module)
        environment = os.environ.copy()
        environment.update(project.environment)
        environment.update(
            {
                "ILLUMINATE_TOKEN": token,
                "ILLUMINATE_READY_FILE": str(ready_path),
                "ILLUMINATE_SCENE_ID": scene_id,
                "ILLUMINATE_RUN_DIR": str(artifacts.root),
                "ILLUMINATE_VISIBLE": "1" if visible else "0",
            }
        )
        popen_options: dict[str, Any] = {
            "cwd": str(project.cwd),
            "env": environment,
        }
        if os.name == "nt" and not visible:
            popen_options["creationflags"] = subprocess.CREATE_NO_WINDOW
        process = self._process_factory(list(argv), **popen_options)
        client = None
        try:
            address = self._await_readiness(process, ready_path)
            try:
                client = self._bridge_connector(address, token, timeout=self._startup_timeout)
            except Exception as exc:
                raise SessionError("bridge connection failed") from exc
        except BaseException:
            ready_path.unlink(missing_ok=True)
            if client is not None:
                client.close()
            self._stop_process(process, request_graceful=False)
            raise
        finally:
            ready_path.unlink(missing_ok=True)
        session = Session(
            session_id=uuid.uuid4().hex,
            project_id=project_id,
            scene_id=scene_id,
            run_artifacts=artifacts,
            launch_argv=argv,
            readiness_path=ready_path,
            process=process,
            client=client,
        )
        artifacts.write_json(
            "session.json",
            {
                "session_id": session.session_id,
                "project_id": project_id,
                "scene_id": scene_id,
                "launch_argv": list(argv),
                "visible": bool(visible),
            },
        )
        self._sessions[session.session_id] = session
        return session

    def require(self, session_id: str) -> Session:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise SessionError(f"session {session_id!r} is not active") from exc

    def close(self, session_id: str, *, discard_unapplied: bool) -> None:
        session = self.require(session_id)
        if session.dirty and not discard_unapplied:
            raise SessionDirtyError("session has unapplied changes; explicit discard is required")
        try:
            try:
                session.client.request(Operation.CLOSE_SCENE, {})
            except BaseException:
                pass
            self._stop_process(session.process, request_graceful=True)
        finally:
            try:
                session.client.close()
            finally:
                self._sessions.pop(session_id, None)

    def _await_readiness(self, process: Any, path: Path) -> BridgeAddress:
        deadline = time.monotonic() + self._startup_timeout
        while time.monotonic() < deadline:
            exit_code = process.poll()
            if exit_code is not None:
                raise SessionError(f"workbench exited with code {exit_code} before readiness")
            if path.is_file():
                try:
                    document = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    time.sleep(self._poll_interval)
                    continue
                if set(document) != {"version", "host", "port"}:
                    raise SessionError("invalid bridge readiness record")
                if document["version"] != 1 or document["host"] != "127.0.0.1":
                    raise SessionError("invalid bridge readiness address")
                port = document["port"]
                if type(port) is not int or not 1 <= port <= 65535:
                    raise SessionError("invalid bridge readiness port")
                return BridgeAddress("127.0.0.1", port)
            time.sleep(self._poll_interval)
        raise SessionError("workbench startup timed out")

    def _stop_process(self, process: Any, *, request_graceful: bool) -> None:
        if process.poll() is not None:
            return
        if request_graceful:
            try:
                process.wait(timeout=self._graceful_timeout)
                return
            except subprocess.TimeoutExpired:
                pass
        process.terminate()
        try:
            process.wait(timeout=self._terminate_timeout)
            return
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=self._terminate_timeout)
