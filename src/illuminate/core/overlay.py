"""Atomic, revisioned in-memory scene edits."""

from __future__ import annotations

from typing import Protocol

from .edits import AppliedBatch, EditBatch, EditKind, EditOperation
from .scene import EditableProperty, SceneRegistry, SceneRegistryError


class EditRejectedError(ValueError):
    pass


class OverlayConflictError(EditRejectedError):
    pass


class MutationPort(Protocol):
    def validate(self, operation: EditOperation, registry: SceneRegistry) -> None: ...
    def inverse(self, operation: EditOperation) -> EditOperation: ...
    def apply(self, operation: EditOperation) -> None: ...


_REQUIRED_PROPERTY = {
    EditKind.SET_POSITION: EditableProperty.TRANSFORM,
    EditKind.SET_HPR: EditableProperty.TRANSFORM,
    EditKind.SET_SCALE: EditableProperty.TRANSFORM,
    EditKind.SET_COLOR_SCALE: EditableProperty.COLOR,
    EditKind.CLEAR_COLOR_SCALE: EditableProperty.COLOR,
    EditKind.SET_VISIBILITY: EditableProperty.VISIBILITY,
    EditKind.SET_LIGHT_COLOR: EditableProperty.LIGHT,
    EditKind.SET_LIGHT_INTENSITY: EditableProperty.LIGHT,
    EditKind.SET_LIGHT_ATTENUATION: EditableProperty.LIGHT,
    EditKind.SET_PARAMETER: EditableProperty.PARAMETER,
    EditKind.CREATE_PRIMITIVE: EditableProperty.PRIMITIVE,
    EditKind.UPDATE_PRIMITIVE: EditableProperty.PRIMITIVE,
    EditKind.REMOVE_PRIMITIVE: EditableProperty.PRIMITIVE,
}


class Overlay:
    def __init__(self) -> None:
        self._revision = 0
        self._active: list[AppliedBatch] = []
        self._audit: list[AppliedBatch] = []

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def active_operations(self) -> tuple[EditOperation, ...]:
        return tuple(
            operation
            for batch in self._active
            for operation in batch.operations
        )

    def preview(
        self,
        batch: EditBatch,
        registry: SceneRegistry,
        mutator: MutationPort,
    ) -> AppliedBatch:
        self._require_revision(batch.expected_revision)
        if not batch.operations:
            raise EditRejectedError("edit batch cannot be empty")

        inverses: list[EditOperation] = []
        try:
            for operation in batch.operations:
                node = registry.require(operation.node_id)
                required = _REQUIRED_PROPERTY[operation.kind]
                if required not in node.editable:
                    raise EditRejectedError(
                        f"{operation.kind.value} requires editable {required.value}"
                    )
                mutator.validate(operation, registry)
                inverses.append(mutator.inverse(operation))
        except SceneRegistryError as exc:
            raise EditRejectedError(str(exc)) from exc

        applied_count = 0
        try:
            for operation in batch.operations:
                mutator.apply(operation)
                applied_count += 1
        except Exception:
            for inverse in reversed(inverses[:applied_count]):
                mutator.apply(inverse)
            raise

        self._revision += 1
        applied = AppliedBatch(
            self._revision,
            tuple(batch.operations),
            tuple(inverses),
        )
        self._active.append(applied)
        self._audit.append(applied)
        return applied

    def undo(
        self,
        expected_revision: int,
        scope: str,
        mutator: MutationPort,
    ) -> int:
        self._require_revision(expected_revision)
        if not self._active:
            raise EditRejectedError("there is nothing to undo")
        if scope not in {"latest", "all"}:
            raise EditRejectedError("undo scope must be latest or all")
        selected = self._active[-1:] if scope == "latest" else self._active[:]
        for batch in reversed(selected):
            completed: list[tuple[EditOperation, EditOperation]] = []
            try:
                for original, inverse in reversed(
                    tuple(zip(batch.operations, batch.inverses, strict=True))
                ):
                    mutator.apply(inverse)
                    completed.append((original, inverse))
            except Exception:
                for original, _inverse in reversed(completed):
                    mutator.apply(original)
                raise
        del self._active[-len(selected) :]
        self._revision += 1
        return self._revision

    def _require_revision(self, expected: int) -> None:
        if expected != self._revision:
            raise OverlayConflictError(
                f"expected revision {expected}; current revision is {self._revision}"
            )

