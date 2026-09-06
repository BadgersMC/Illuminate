"""Explicit comparison, validation, and approval gate for source persistence."""

from __future__ import annotations

from dataclasses import dataclass, replace

from illuminate.adapters import ApplyAdapter, ApplyReport
from illuminate.core.edits import EditOperation

from .artifacts import RunArtifacts


class ApplyBlockedError(RuntimeError):
    pass


class SourceConflictError(ApplyBlockedError):
    pass


@dataclass(frozen=True)
class ApplyState:
    revision: int
    operations: tuple[EditOperation, ...]
    baseline_view_ids: frozenset[str]
    final_view_ids: frozenset[str]


class ApplyGate:
    def __init__(
        self,
        adapter: ApplyAdapter,
        scene_id: str,
        base_fingerprint: str,
        state: ApplyState,
        artifacts: RunArtifacts,
    ) -> None:
        self._adapter = adapter
        self._scene_id = scene_id
        self._base_fingerprint = base_fingerprint
        self.state = state
        self.artifacts = artifacts

    def apply(self, expected_revision: int, approval_note: str) -> ApplyReport:
        if not isinstance(approval_note, str) or not approval_note.strip():
            raise ApplyBlockedError("a non-empty approval note is required")
        if expected_revision != self.state.revision:
            raise ApplyBlockedError(
                f"revision conflict: expected {expected_revision}, current {self.state.revision}"
            )
        if not self.state.operations:
            raise ApplyBlockedError("there are no preview changes to apply")
        if (
            not self.state.baseline_view_ids
            or self.state.baseline_view_ids != self.state.final_view_ids
        ):
            raise ApplyBlockedError("comparison requires matching non-empty baseline and final views")

        plan = self._adapter.plan(
            self._scene_id,
            self._base_fingerprint,
            self.state.operations,
        )
        validation = self._adapter.validate(plan)
        if not validation.ok:
            details = "; ".join(validation.errors) or "adapter validation failed"
            raise ApplyBlockedError(details)
        report = self._adapter.persist(plan)
        self.artifacts.write_json(
            "apply-report.json",
            {
                "scene_id": report.scene_id,
                "revision": self.state.revision,
                "approval_note": approval_note.strip(),
                "baseline_view_ids": sorted(self.state.baseline_view_ids),
                "final_view_ids": sorted(self.state.final_view_ids),
                "changed_node_ids": list(report.changed_node_ids),
                "destination_paths": [str(path.resolve()) for path in report.destination_paths],
            },
        )
        self.state = replace(self.state, operations=())
        return report
