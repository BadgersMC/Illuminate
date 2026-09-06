from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from illuminate.core.edits import EditBatch, EditKind, EditOperation
from illuminate.core.overlay import (
    EditRejectedError,
    Overlay,
    OverlayConflictError,
)
from illuminate.core.scene import EditableProperty, SceneRegistry


@dataclass
class RecordingMutator:
    values: dict[str, object] = field(
        default_factory=lambda: {
            "door.position": [0.0, 0.0, 0.0],
            "door.visibility": True,
            "protected.position": [0.0, 0.0, 0.0],
        }
    )
    fail_validate_node: str | None = None
    fail_apply_node: str | None = None

    def validate(self, operation: EditOperation, registry: SceneRegistry) -> None:
        registry.require(operation.node_id)
        if operation.node_id == self.fail_validate_node:
            raise EditRejectedError(f"cannot edit {operation.node_id}")

    def inverse(self, operation: EditOperation) -> EditOperation:
        key = self._key(operation)
        return EditOperation(operation.node_id, operation.kind, self.values[key])

    def apply(self, operation: EditOperation) -> None:
        if operation.node_id == self.fail_apply_node:
            raise EditRejectedError(f"cannot apply {operation.node_id}")
        self.values[self._key(operation)] = operation.value

    @staticmethod
    def _key(operation: EditOperation) -> str:
        suffix = {
            EditKind.SET_POSITION: "position",
            EditKind.SET_VISIBILITY: "visibility",
        }[operation.kind]
        return f"{operation.node_id}.{suffix}"


def fixture() -> tuple[Overlay, SceneRegistry, RecordingMutator]:
    registry = SceneRegistry("waystation")
    registry.register("root", None, "root", frozenset(), object())
    registry.register(
        "door",
        "root",
        "model",
        {EditableProperty.TRANSFORM, EditableProperty.VISIBILITY},
        object(),
    )
    registry.register(
        "protected",
        "root",
        "model",
        {EditableProperty.TRANSFORM},
        object(),
    )
    return Overlay(), registry, RecordingMutator()


def test_preview_records_inverse_and_advances_revision() -> None:
    overlay, registry, mutator = fixture()
    batch = EditBatch(
        0,
        (EditOperation("door", EditKind.SET_POSITION, [1.0, 2.0, 3.0]),),
    )

    applied = overlay.preview(batch, registry, mutator)

    assert applied.revision == 1
    assert overlay.revision == 1
    assert mutator.values["door.position"] == [1.0, 2.0, 3.0]
    assert applied.inverses[0].value == [0.0, 0.0, 0.0]


def test_preview_rejects_stale_revision_without_mutation() -> None:
    overlay, registry, mutator = fixture()

    with pytest.raises(
        OverlayConflictError,
        match="expected revision 1.*current revision is 0",
    ):
        overlay.preview(
            EditBatch(1, (EditOperation("door", EditKind.SET_POSITION, [1, 2, 3]),)),
            registry,
            mutator,
        )

    assert mutator.values["door.position"] == [0.0, 0.0, 0.0]


def test_batch_validation_is_atomic() -> None:
    overlay, registry, mutator = fixture()
    batch = EditBatch(
        0,
        (
            EditOperation("door", EditKind.SET_POSITION, [1.0, 2.0, 3.0]),
            EditOperation("protected", EditKind.SET_VISIBILITY, False),
        ),
    )

    with pytest.raises(EditRejectedError, match="visibility"):
        overlay.preview(batch, registry, mutator)

    assert overlay.revision == 0
    assert mutator.values["door.position"] == [0.0, 0.0, 0.0]


def test_apply_failure_rolls_back_earlier_operation() -> None:
    overlay, registry, mutator = fixture()
    mutator.fail_apply_node = "protected"
    batch = EditBatch(
        0,
        (
            EditOperation("door", EditKind.SET_POSITION, [1.0, 2.0, 3.0]),
            EditOperation("protected", EditKind.SET_POSITION, [4.0, 5.0, 6.0]),
        ),
    )

    with pytest.raises(EditRejectedError):
        overlay.preview(batch, registry, mutator)

    assert overlay.revision == 0
    assert mutator.values["door.position"] == [0.0, 0.0, 0.0]


def test_undo_latest_restores_values_and_creates_a_new_revision() -> None:
    overlay, registry, mutator = fixture()
    overlay.preview(
        EditBatch(0, (EditOperation("door", EditKind.SET_POSITION, [1, 2, 3]),)),
        registry,
        mutator,
    )

    revision = overlay.undo(1, "latest", mutator)

    assert revision == 2
    assert overlay.revision == 2
    assert mutator.values["door.position"] == [0.0, 0.0, 0.0]
    assert overlay.active_operations == ()


def test_empty_batch_and_undo_without_history_are_rejected() -> None:
    overlay, registry, mutator = fixture()
    with pytest.raises(EditRejectedError, match="empty"):
        overlay.preview(EditBatch(0, ()), registry, mutator)
    with pytest.raises(EditRejectedError, match="nothing"):
        overlay.undo(0, "latest", mutator)
