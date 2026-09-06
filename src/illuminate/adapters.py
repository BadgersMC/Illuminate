"""Project-owned persistence contracts for approved Illuminate edits."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from illuminate.core.edits import EditOperation


@dataclass(frozen=True)
class ApplyPlan:
    scene_id: str
    base_fingerprint: str
    operations: tuple[EditOperation, ...]
    destination_paths: tuple[Path, ...]


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    errors: tuple[str, ...]


@dataclass(frozen=True)
class ApplyReport:
    scene_id: str
    changed_node_ids: tuple[str, ...]
    destination_paths: tuple[Path, ...]


class ApplyAdapter(Protocol):
    def plan(
        self,
        scene_id: str,
        base_fingerprint: str,
        operations: Sequence[EditOperation],
    ) -> ApplyPlan: ...

    def validate(self, plan: ApplyPlan) -> ValidationReport: ...

    def persist(self, plan: ApplyPlan) -> ApplyReport: ...
