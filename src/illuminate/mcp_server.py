"""Official MCP v2 server exposing Illuminate's eight bounded operations."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
from typing import Any, Callable

from mcp.server.mcpserver import MCPServer

from illuminate.core.edits import EditKind, EditOperation
from illuminate.protocol import Operation, Response
from illuminate.server.apply import ApplyGate, ApplyState
from illuminate.server.artifacts import RunArtifacts
from illuminate.server.projects import ProjectRegistry
from illuminate.server.sessions import Session, SessionManager


class IlluminateServiceError(RuntimeError):
    pass


class IlluminateService:
    def __init__(
        self,
        manager: SessionManager,
        runs_root: Path | str,
        *,
        apply_gate_factory: Callable[[Session], Any],
    ) -> None:
        self._manager = manager
        self._runs_root = Path(runs_root).resolve()
        self._apply_gate_factory = apply_gate_factory
        self._gates: dict[str, Any] = {}
        self._preview_batches: dict[str, list[tuple[EditOperation, ...]]] = {}

    def launch_scene(self, project_id: str, scene_id: str, visible: bool = True) -> dict[str, Any]:
        """Launch one trusted registered scene; never accepts a command or working directory."""
        run = RunArtifacts.create_unique(self._runs_root)
        session = self._manager.launch(project_id, scene_id, run.root, visible)
        self._gates[session.session_id] = self._apply_gate_factory(session)
        self._preview_batches[session.session_id] = []
        return {
            "session_id": session.session_id,
            "project_id": session.project_id,
            "scene_id": session.scene_id,
            "run_dir": str(session.run_artifacts.root),
        }

    def scene_summary(self, session_id: str, depth: int = 1) -> dict[str, Any]:
        """Return a compact semantic summary without raw Panda objects."""
        if not 0 <= depth <= 8:
            raise IlluminateServiceError("depth must be between 0 and 8")
        return self._forward(session_id, Operation.SCENE_SUMMARY, {"depth": depth})

    def inspect_nodes(self, session_id: str, node_ids: list[str]) -> dict[str, Any]:
        """Inspect only explicitly named semantic scene nodes."""
        if not node_ids or len(node_ids) > 128:
            raise IlluminateServiceError("node_ids must contain between 1 and 128 IDs")
        return self._forward(session_id, Operation.INSPECT_NODES, {"node_ids": node_ids})

    def preview_changes(
        self,
        session_id: str,
        expected_revision: int,
        operations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Temporarily preview one atomic, revision-checked batch; writes no source files."""
        if not operations or len(operations) > 256:
            raise IlluminateServiceError("operations must contain between 1 and 256 edits")
        parsed = tuple(
            EditOperation(str(item["node_id"]), EditKind(item["kind"]), item.get("value"))
            for item in operations
        )
        result = self._forward(
            session_id,
            Operation.PREVIEW_CHANGES,
            {"expected_revision": expected_revision, "operations": operations},
        )
        session = self._manager.require(session_id)
        revision = int(result["revision"])
        session.mark_dirty(revision)
        self._preview_batches[session_id].append(parsed)
        self._update_gate_state(session_id, revision=revision, operations=self._active_ops(session_id))
        return result

    def capture_views(
        self,
        session_id: str,
        view_ids: list[str],
        comparison_stage: str,
    ) -> dict[str, Any]:
        """Capture registered canonical views and record them as baseline or final comparison."""
        if comparison_stage not in {"baseline", "final"}:
            raise IlluminateServiceError("comparison_stage must be baseline or final")
        if not view_ids or len(view_ids) > 32 or len(set(view_ids)) != len(view_ids):
            raise IlluminateServiceError("view_ids must contain 1-32 unique registered IDs")
        result = self._forward(session_id, Operation.CAPTURE_VIEWS, {"view_ids": view_ids})
        field = "baseline_view_ids" if comparison_stage == "baseline" else "final_view_ids"
        self._update_gate_state(session_id, **{field: frozenset(view_ids)})
        return result

    def undo_changes(
        self,
        session_id: str,
        expected_revision: int,
        scope: str = "latest",
    ) -> dict[str, Any]:
        """Undo the latest or all temporary edits while retaining an audit revision."""
        if scope not in {"latest", "all"}:
            raise IlluminateServiceError("scope must be latest or all")
        result = self._forward(
            session_id,
            Operation.UNDO_CHANGES,
            {"expected_revision": expected_revision, "scope": scope},
        )
        batches = self._preview_batches[session_id]
        if scope == "all":
            batches.clear()
        elif batches:
            batches.pop()
        revision = int(result["revision"])
        session = self._manager.require(session_id)
        if batches:
            session.mark_dirty(revision)
        else:
            session.mark_clean(revision)
        self._update_gate_state(session_id, revision=revision, operations=self._active_ops(session_id))
        return result

    def apply_changes(
        self,
        session_id: str,
        expected_revision: int,
        approval_note: str,
    ) -> dict[str, Any]:
        """Persist only after current-revision, same-view comparison, validation, and explicit approval."""
        session = self._manager.require(session_id)
        report = self._gates[session_id].apply(expected_revision, approval_note)
        session.mark_clean(expected_revision)
        return {
            "scene_id": report.scene_id,
            "changed_node_ids": list(report.changed_node_ids),
            "destination_paths": [str(path.resolve()) for path in report.destination_paths],
        }

    def close_scene(self, session_id: str, discard_unapplied: bool = False) -> dict[str, Any]:
        """Close the workbench, requiring explicit discard when temporary edits remain."""
        self._manager.close(session_id, discard_unapplied=discard_unapplied)
        self._gates.pop(session_id, None)
        self._preview_batches.pop(session_id, None)
        return {"closed": True, "session_id": session_id}

    def _forward(self, session_id: str, operation: Operation, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._manager.require(session_id)
        response: Response = session.client.request(operation, payload)
        if not response.ok:
            raise IlluminateServiceError(response.error_message or "bridge operation failed")
        return dict(response.result or {})

    def _active_ops(self, session_id: str) -> tuple[EditOperation, ...]:
        return tuple(op for batch in self._preview_batches[session_id] for op in batch)

    def _update_gate_state(self, session_id: str, **changes: Any) -> None:
        gate = self._gates[session_id]
        state = getattr(gate, "state", None)
        if isinstance(state, ApplyState):
            gate.state = replace(state, **changes)


def create_mcp_server(service: IlluminateService) -> MCPServer:
    server = MCPServer(
        "illuminate",
        description="A bounded semantic Panda3D scene workbench with explicit apply approval.",
    )

    server.tool()(service.launch_scene)
    server.tool()(service.scene_summary)
    server.tool()(service.inspect_nodes)
    server.tool()(service.preview_changes)
    server.tool()(service.capture_views)
    server.tool()(service.undo_changes)
    server.tool()(service.apply_changes)
    server.tool()(service.close_scene)
    return server


class _UnavailableApplyGate:
    def apply(self, expected_revision: int, approval_note: str) -> Any:
        raise IlluminateServiceError("project has no registered apply adapter")


def _unconfigured_gate(_session: Session) -> Any:
    return _UnavailableApplyGate()


def main() -> None:
    projects_path = os.environ.get("ILLUMINATE_PROJECTS_FILE")
    runs_root = os.environ.get("ILLUMINATE_RUNS_ROOT")
    if not projects_path or not runs_root:
        raise SystemExit("ILLUMINATE_PROJECTS_FILE and ILLUMINATE_RUNS_ROOT are required")
    registry = ProjectRegistry.load(projects_path)
    service = IlluminateService(
        SessionManager(registry),
        runs_root,
        apply_gate_factory=_unconfigured_gate,
    )
    create_mcp_server(service).run("stdio")


if __name__ == "__main__":
    main()
