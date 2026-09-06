from __future__ import annotations

import asyncio
from pathlib import Path

from illuminate.protocol import Operation, Response
from illuminate.server.artifacts import RunArtifacts
from illuminate.mcp_server import IlluminateService, create_mcp_server


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def request(self, operation, payload=None):
        self.calls.append((operation, payload or {}))
        result = {"forwarded": operation.value}
        if operation is Operation.PREVIEW_CHANGES:
            result = {"revision": 1, "changed_node_ids": ["door"]}
        elif operation is Operation.UNDO_CHANGES:
            result = {"revision": 2, "dirty": False}
        elif operation is Operation.CAPTURE_VIEWS:
            result = {"captures": [{"view_id": value} for value in payload["view_ids"]]}
        return Response.success("fake", result)


class FakeSession:
    def __init__(self, run_dir: Path) -> None:
        self.session_id = "s1"
        self.project_id = "fixture"
        self.scene_id = "triangle"
        self.run_artifacts = RunArtifacts(run_dir)
        self.client = FakeClient()
        self.revision = 0
        self.dirty = False

    def mark_dirty(self, revision):
        self.revision = revision
        self.dirty = True

    def mark_clean(self, revision):
        self.revision = revision
        self.dirty = False


class FakeManager:
    def __init__(self, tmp_path) -> None:
        self.tmp_path = tmp_path
        self.session = None
        self.launch_args = None
        self.close_args = None

    def launch(self, project_id, scene_id, run_dir, visible):
        self.launch_args = (project_id, scene_id, Path(run_dir), visible)
        self.session = FakeSession(Path(run_dir))
        return self.session

    def require(self, session_id):
        assert session_id == "s1"
        return self.session

    def close(self, session_id, discard_unapplied):
        self.close_args = (session_id, discard_unapplied)


class FakeGate:
    def __init__(self) -> None:
        self.calls = []

    def apply(self, expected_revision, approval_note):
        self.calls.append((expected_revision, approval_note))
        return type(
            "Report",
            (),
            {
                "scene_id": "triangle",
                "changed_node_ids": ("door",),
                "destination_paths": (Path("C:/fixture/scene.json"),),
            },
        )()


def test_service_exercises_exactly_eight_bounded_operations(tmp_path) -> None:
    manager = FakeManager(tmp_path)
    gate = FakeGate()
    service = IlluminateService(manager, tmp_path / "runs", apply_gate_factory=lambda session: gate)

    launched = service.launch_scene("fixture", "triangle", visible=False)
    assert launched["session_id"] == "s1"
    assert manager.launch_args[2].parent == (tmp_path / "runs").resolve()

    assert service.scene_summary("s1", depth=2)["forwarded"] == "scene_summary"
    assert service.inspect_nodes("s1", ["door"])["forwarded"] == "inspect_nodes"
    preview = service.preview_changes(
        "s1", 0, [{"node_id": "door", "kind": "set_position", "value": [1, 2, 3]}]
    )
    assert preview["revision"] == 1
    assert service.capture_views("s1", ["arrival"], "baseline")["captures"]
    assert service.capture_views("s1", ["arrival"], "final")["captures"]
    assert service.undo_changes("s1", 1, "all")["revision"] == 2
    assert manager.session.revision == 2
    assert manager.session.dirty is False
    applied = service.apply_changes("s1", 2, "approved after review")
    assert applied["changed_node_ids"] == ["door"]
    assert gate.calls == [(2, "approved after review")]
    assert manager.session.revision == 2
    assert manager.session.dirty is False
    assert service.close_scene("s1", discard_unapplied=True)["closed"]
    assert manager.close_args == ("s1", True)

    forwarded = [operation for operation, _payload in manager.session.client.calls]
    assert forwarded == [
        Operation.SCENE_SUMMARY,
        Operation.INSPECT_NODES,
        Operation.PREVIEW_CHANGES,
        Operation.CAPTURE_VIEWS,
        Operation.CAPTURE_VIEWS,
        Operation.UNDO_CHANGES,
    ]


def test_mcp_server_exposes_only_the_public_tool_surface(tmp_path) -> None:
    service = IlluminateService(
        FakeManager(tmp_path),
        tmp_path / "runs",
        apply_gate_factory=lambda session: FakeGate(),
    )
    server = create_mcp_server(service)

    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}

    assert names == {
        "launch_scene",
        "scene_summary",
        "inspect_nodes",
        "preview_changes",
        "capture_views",
        "undo_changes",
        "apply_changes",
        "close_scene",
    }
    assert names.isdisjoint({"eval", "shell", "read_file", "write_file"})
