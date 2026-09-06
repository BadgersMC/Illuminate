"""Closed request dispatcher for one registered Panda3D scene."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping

from illuminate.core.edits import EditBatch, EditKind, EditOperation
from illuminate.core.overlay import EditRejectedError, Overlay, OverlayConflictError
from illuminate.core.scene import SceneRegistry, SceneRegistryError
from illuminate.protocol import ErrorCode, Operation, Request, Response

from .capture import CameraView, capture_views
from .mutator import PandaMutator
from .registration import PandaSceneRegistration


class PandaCommandDispatcher:
    def __init__(
        self,
        *,
        registration: PandaSceneRegistration,
        overlay: Overlay,
        mutator: PandaMutator,
        base,
        views: Mapping[str, CameraView],
        capture_dir: Path,
        close_callback: Callable[[], None] | None = None,
    ) -> None:
        self.registration = registration
        self._overlay = overlay
        self._mutator = mutator
        self._base = base
        self._views = dict(views)
        self._capture_dir = capture_dir
        self._close_callback = close_callback

    def dispatch(self, request: Request, registry: SceneRegistry) -> Response:
        if registry is not self.registration.registry:
            return Response.failure(
                request.request_id,
                ErrorCode.INVALID_REQUEST,
                "dispatcher registry mismatch",
            )
        if request.operation in {Operation.LAUNCH_SCENE, Operation.APPLY_CHANGES}:
            return Response.failure(
                request.request_id,
                ErrorCode.UNKNOWN_OPERATION,
                "operation is server-owned",
            )
        try:
            result = self._dispatch(request)
            return Response.success(request.request_id, result)
        except OverlayConflictError as exc:
            return Response.failure(
                request.request_id, ErrorCode.REVISION_CONFLICT, str(exc)
            )
        except (EditRejectedError, SceneRegistryError, KeyError, TypeError, ValueError) as exc:
            return Response.failure(request.request_id, ErrorCode.EDIT_REJECTED, str(exc))

    def _dispatch(self, request: Request) -> dict[str, object]:
        if request.operation is Operation.SCENE_SUMMARY:
            self._require_fields(request.payload, optional={"depth"})
            return {
                **self.registration.registry.summary(depth=int(request.payload.get("depth", 1))),
                "revision": self._overlay.revision,
                "dirty": bool(self._overlay.active_operations),
            }
        if request.operation is Operation.INSPECT_NODES:
            self._require_fields(request.payload, required={"node_ids"})
            node_ids = request.payload["node_ids"]
            if not isinstance(node_ids, list):
                raise ValueError("node_ids must be a list")
            return {"nodes": [self._inspect(str(node_id)) for node_id in node_ids]}
        if request.operation is Operation.PREVIEW_CHANGES:
            self._require_fields(
                request.payload,
                required={"expected_revision", "operations"},
            )
            operations = tuple(
                EditOperation(
                    str(item["node_id"]),
                    EditKind(item["kind"]),
                    item.get("value"),
                )
                for item in request.payload["operations"]
            )
            applied = self._overlay.preview(
                EditBatch(int(request.payload["expected_revision"]), operations),
                self.registration.registry,
                self._mutator,
            )
            return {
                "revision": applied.revision,
                "changed_node_ids": list(dict.fromkeys(op.node_id for op in operations)),
            }
        if request.operation is Operation.UNDO_CHANGES:
            self._require_fields(
                request.payload,
                required={"expected_revision"},
                optional={"scope"},
            )
            revision = self._overlay.undo(
                int(request.payload["expected_revision"]),
                str(request.payload.get("scope", "latest")),
                self._mutator,
            )
            return {"revision": revision, "dirty": bool(self._overlay.active_operations)}
        if request.operation is Operation.CAPTURE_VIEWS:
            self._require_fields(request.payload, required={"view_ids"})
            requested = tuple(self._views[str(view_id)] for view_id in request.payload["view_ids"])
            records = capture_views(
                self._base,
                self.registration,
                requested,
                self._capture_dir,
            )
            return {
                "captures": [
                    {
                        "view_id": record.view_id,
                        "path": str(record.path),
                        "width": record.width,
                        "height": record.height,
                        "sha256": record.sha256,
                    }
                    for record in records
                ]
            }
        if request.operation is Operation.CLOSE_SCENE:
            self._require_fields(request.payload)
            if self._close_callback is not None:
                self._close_callback()
            return {"closing": True}
        raise ValueError("operation is not handled by the Panda dispatcher")

    def _inspect(self, node_id: str) -> dict[str, object]:
        semantic = self.registration.registry.require(node_id)
        node = self.registration.node_path(node_id)
        if node.is_empty():
            raise EditRejectedError(f"node {node_id!r} was removed")
        return {
            "id": semantic.node_id,
            "kind": semantic.kind,
            "parent_id": semantic.parent_id,
            "editable": sorted(item.value for item in semantic.editable),
            "position": [float(value) for value in node.get_pos()],
            "hpr": [float(value) for value in node.get_hpr()],
            "scale": [float(value) for value in node.get_scale()],
            "visible": not node.is_hidden(),
        }

    @staticmethod
    def _require_fields(
        payload,
        *,
        required: set[str] | None = None,
        optional: set[str] | None = None,
    ) -> None:
        required = required or set()
        optional = optional or set()
        fields = set(payload)
        if not required.issubset(fields) or fields - required - optional:
            raise ValueError(
                f"payload fields must include {sorted(required)} and may include {sorted(optional)}"
            )
