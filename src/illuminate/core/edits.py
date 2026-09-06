"""Typed temporary scene edit values."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class EditKind(Enum):
    SET_POSITION = "set_position"
    SET_HPR = "set_hpr"
    SET_SCALE = "set_scale"
    SET_COLOR_SCALE = "set_color_scale"
    CLEAR_COLOR_SCALE = "clear_color_scale"
    SET_VISIBILITY = "set_visibility"
    SET_LIGHT_COLOR = "set_light_color"
    SET_LIGHT_INTENSITY = "set_light_intensity"
    SET_LIGHT_ATTENUATION = "set_light_attenuation"
    SET_PARAMETER = "set_parameter"
    CREATE_PRIMITIVE = "create_primitive"
    UPDATE_PRIMITIVE = "update_primitive"
    REMOVE_PRIMITIVE = "remove_primitive"


@dataclass(frozen=True)
class EditOperation:
    node_id: str
    kind: EditKind
    value: Any


@dataclass(frozen=True)
class EditBatch:
    expected_revision: int
    operations: tuple[EditOperation, ...]


@dataclass(frozen=True)
class AppliedBatch:
    revision: int
    operations: tuple[EditOperation, ...]
    inverses: tuple[EditOperation, ...]

