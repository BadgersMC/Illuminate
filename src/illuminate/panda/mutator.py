"""Explicit, bounded Panda3D scene mutations."""

from __future__ import annotations

import math

from panda3d.core import NodePath

from illuminate.core.edits import EditKind, EditOperation
from illuminate.core.overlay import EditRejectedError
from illuminate.core.scene import SceneRegistry

from .registration import PandaSceneRegistration


class PandaMutator:
    def __init__(self, registration: PandaSceneRegistration) -> None:
        self._registration = registration
        self._light_states: dict[str, dict[str, object]] = {}

    def validate(self, operation: EditOperation, registry: SceneRegistry) -> None:
        registry.require(operation.node_id)
        node = self._registration.node_path(operation.node_id)
        if node.is_empty():
            raise EditRejectedError(f"node {operation.node_id!r} was removed")
        if operation.kind in {
            EditKind.SET_POSITION,
            EditKind.SET_HPR,
            EditKind.SET_SCALE,
        }:
            self._finite_vector(operation.value, 3, operation.kind.value)
        elif operation.kind is EditKind.SET_VISIBILITY:
            if type(operation.value) is not bool:
                raise EditRejectedError("visibility must be boolean")
        elif operation.kind is EditKind.SET_COLOR_SCALE:
            self._finite_vector(operation.value, 4, "color scale")
        elif operation.kind is EditKind.SET_LIGHT_COLOR:
            self._require_light(operation.node_id)
            self._finite_vector(operation.value, 4, "light color")
        elif operation.kind is EditKind.SET_LIGHT_INTENSITY:
            self._require_light(operation.node_id)
            if type(operation.value) not in {int, float}:
                raise EditRejectedError("light intensity must be a number")
            if not math.isfinite(float(operation.value)) or float(operation.value) < 0:
                raise EditRejectedError("light intensity must be finite and non-negative")
        elif operation.kind is EditKind.SET_LIGHT_ATTENUATION:
            light = self._require_light(operation.node_id)
            if not hasattr(light, "set_attenuation"):
                raise EditRejectedError("light does not support attenuation")
            attenuation = self._finite_vector(operation.value, 3, "light attenuation")
            if any(value < 0 for value in attenuation):
                raise EditRejectedError("light attenuation must be non-negative")
        elif operation.kind is not EditKind.CLEAR_COLOR_SCALE:
            raise EditRejectedError(f"{operation.kind.value} is not supported by NodePath")

    def inverse(self, operation: EditOperation) -> EditOperation:
        node = self._registration.node_path(operation.node_id)
        if operation.kind is EditKind.SET_POSITION:
            value = list(node.get_pos())
        elif operation.kind is EditKind.SET_HPR:
            value = list(node.get_hpr())
        elif operation.kind is EditKind.SET_SCALE:
            value = list(node.get_scale())
        elif operation.kind is EditKind.SET_VISIBILITY:
            value = not node.is_hidden()
        elif operation.kind in {EditKind.SET_COLOR_SCALE, EditKind.CLEAR_COLOR_SCALE}:
            value = list(node.get_color_scale())
            return EditOperation(operation.node_id, EditKind.SET_COLOR_SCALE, value)
        elif operation.kind is EditKind.SET_LIGHT_COLOR:
            value = list(self._light_state(operation.node_id)["color"])
        elif operation.kind is EditKind.SET_LIGHT_INTENSITY:
            value = self._light_state(operation.node_id)["intensity"]
        elif operation.kind is EditKind.SET_LIGHT_ATTENUATION:
            value = list(self._light_state(operation.node_id)["attenuation"])
        else:
            raise EditRejectedError(f"cannot capture inverse for {operation.kind.value}")
        return EditOperation(operation.node_id, operation.kind, value)

    def apply(self, operation: EditOperation) -> None:
        node: NodePath = self._registration.node_path(operation.node_id)
        if operation.kind is EditKind.SET_POSITION:
            node.set_pos(*operation.value)
        elif operation.kind is EditKind.SET_HPR:
            node.set_hpr(*operation.value)
        elif operation.kind is EditKind.SET_SCALE:
            node.set_scale(*operation.value)
        elif operation.kind is EditKind.SET_VISIBILITY:
            node.show() if operation.value else node.hide()
        elif operation.kind is EditKind.SET_COLOR_SCALE:
            node.set_color_scale(*operation.value)
        elif operation.kind is EditKind.CLEAR_COLOR_SCALE:
            node.clear_color_scale()
        elif operation.kind is EditKind.SET_LIGHT_COLOR:
            state = self._light_state(operation.node_id)
            state["color"] = tuple(float(value) for value in operation.value)
            self._apply_light_color(operation.node_id)
        elif operation.kind is EditKind.SET_LIGHT_INTENSITY:
            state = self._light_state(operation.node_id)
            state["intensity"] = float(operation.value)
            self._apply_light_color(operation.node_id)
        elif operation.kind is EditKind.SET_LIGHT_ATTENUATION:
            state = self._light_state(operation.node_id)
            state["attenuation"] = tuple(float(value) for value in operation.value)
            self._require_light(operation.node_id).set_attenuation(state["attenuation"])
        else:
            raise EditRejectedError(f"cannot apply {operation.kind.value}")

    @staticmethod
    def _finite_vector(value: object, length: int, label: str) -> tuple[float, ...]:
        if not isinstance(value, (list, tuple)) or len(value) != length:
            raise EditRejectedError(f"{label} must contain {length} numbers")
        if any(type(component) not in {int, float} for component in value):
            raise EditRejectedError(f"{label} must contain only numbers")
        result = tuple(float(component) for component in value)
        if not all(math.isfinite(component) for component in result):
            raise EditRejectedError(f"{label} values must be finite")
        return result

    def _require_light(self, node_id: str):
        node = self._registration.node_path(node_id).node()
        if not hasattr(node, "get_color") or not hasattr(node, "set_color"):
            raise EditRejectedError(f"node {node_id!r} is not a light")
        return node

    def _light_state(self, node_id: str) -> dict[str, object]:
        if node_id not in self._light_states:
            light = self._require_light(node_id)
            attenuation = (
                tuple(float(value) for value in light.get_attenuation())
                if hasattr(light, "get_attenuation")
                else (1.0, 0.0, 0.0)
            )
            self._light_states[node_id] = {
                "color": tuple(float(value) for value in light.get_color()),
                "intensity": 1.0,
                "attenuation": attenuation,
            }
        return self._light_states[node_id]

    def _apply_light_color(self, node_id: str) -> None:
        state = self._light_state(node_id)
        color = state["color"]
        intensity = float(state["intensity"])
        self._require_light(node_id).set_color(
            (color[0] * intensity, color[1] * intensity, color[2] * intensity, color[3])
        )
