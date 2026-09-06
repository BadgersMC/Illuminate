"""Semantic registration of Panda3D scene objects."""

from __future__ import annotations

from collections.abc import Iterable

from panda3d.core import NodePath

from illuminate.core.scene import EditableProperty, SceneRegistry


class PandaSceneRegistration:
    def __init__(self, scene_id: str, *, max_summary_nodes: int = 256) -> None:
        self.registry = SceneRegistry(scene_id, max_summary_nodes=max_summary_nodes)

    @property
    def scene_id(self) -> str:
        return self.registry.scene_id

    def add_node(
        self,
        node_id: str,
        node_path: NodePath,
        editable: Iterable[EditableProperty],
        *,
        parent_id: str | None = None,
        kind: str = "node",
    ) -> None:
        self.registry.register(node_id, parent_id, kind, editable, node_path)

    def node_path(self, node_id: str) -> NodePath:
        return self.registry.handle(node_id)

