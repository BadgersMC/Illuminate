"""Semantic scene registry with no renderer dependency."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from illuminate.protocol import MAX_IDENTIFIER_BYTES


class EditableProperty(Enum):
    TRANSFORM = "transform"
    COLOR = "color"
    VISIBILITY = "visibility"
    LIGHT = "light"
    PARAMETER = "parameter"
    PRIMITIVE = "primitive"


class SceneRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class SemanticNode:
    node_id: str
    parent_id: str | None
    kind: str
    editable: frozenset[EditableProperty]


class SceneRegistry:
    def __init__(self, scene_id: str, *, max_summary_nodes: int = 256) -> None:
        self._validate_id(scene_id, "scene id")
        if max_summary_nodes < 1:
            raise SceneRegistryError("max_summary_nodes must be positive")
        self.scene_id = scene_id
        self.max_summary_nodes = max_summary_nodes
        self._nodes: dict[str, SemanticNode] = {}
        self._handles: dict[str, Any] = {}

    def register(
        self,
        node_id: str,
        parent_id: str | None,
        kind: str,
        editable: Iterable[EditableProperty],
        handle: Any,
    ) -> SemanticNode:
        self._validate_id(node_id, "node id")
        self._validate_id(kind, "node kind")
        if node_id in self._nodes:
            raise SceneRegistryError(f"node {node_id!r} is already registered")
        if parent_id is not None and parent_id not in self._nodes:
            raise SceneRegistryError(f"parent {parent_id!r} is not registered")
        editable_set = frozenset(editable)
        if not all(isinstance(item, EditableProperty) for item in editable_set):
            raise SceneRegistryError("editable entries must be EditableProperty values")
        node = SemanticNode(node_id, parent_id, kind, editable_set)
        self._nodes[node_id] = node
        self._handles[node_id] = handle
        return node

    def require(self, node_id: str) -> SemanticNode:
        try:
            return self._nodes[node_id]
        except KeyError as exc:
            raise SceneRegistryError(f"node {node_id!r} is not registered") from exc

    def handle(self, node_id: str) -> Any:
        self.require(node_id)
        return self._handles[node_id]

    def summary(self, *, depth: int = 1) -> dict[str, object]:
        if depth < 0:
            raise SceneRegistryError("depth cannot be negative")
        eligible = [node for node in self._nodes.values() if self._depth(node) <= depth]
        visible = eligible[: self.max_summary_nodes]
        return {
            "scene_id": self.scene_id,
            "nodes": [
                {
                    "id": node.node_id,
                    "parent_id": node.parent_id,
                    "kind": node.kind,
                    "editable": sorted(item.value for item in node.editable),
                }
                for node in visible
            ],
            "truncated": len(eligible) > len(visible),
        }

    def _depth(self, node: SemanticNode) -> int:
        depth = 0
        parent_id = node.parent_id
        while parent_id is not None:
            depth += 1
            parent_id = self._nodes[parent_id].parent_id
        return depth

    @staticmethod
    def _validate_id(value: object, label: str) -> None:
        if not isinstance(value, str) or not value:
            raise SceneRegistryError(f"{label} is required")
        if len(value.encode("utf-8")) > MAX_IDENTIFIER_BYTES:
            raise SceneRegistryError(
                f"{label} exceeds {MAX_IDENTIFIER_BYTES} UTF-8 bytes"
            )

