from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os

import pytest

from illuminate.adapters import ApplyPlan, ApplyReport, ValidationReport
from illuminate.core.edits import EditKind, EditOperation
from illuminate.server.apply import (
    ApplyBlockedError,
    ApplyGate,
    ApplyState,
    SourceConflictError,
)
from illuminate.server.artifacts import RunArtifacts


class FixtureAdapter:
    def __init__(self, target) -> None:
        self.target = target
        self.persist_calls = 0

    def plan(self, scene_id, base_fingerprint, operations):
        current = hashlib.sha256(self.target.read_bytes()).hexdigest()
        if current != base_fingerprint:
            raise SourceConflictError("source changed since preview began")
        return ApplyPlan(
            scene_id=scene_id,
            base_fingerprint=base_fingerprint,
            operations=tuple(operations),
            destination_paths=(self.target.resolve(),),
        )

    def validate(self, plan):
        return ValidationReport(True, ())

    def persist(self, plan):
        temporary = self.target.with_suffix(".tmp")
        temporary.write_text(json.dumps({"applied": len(plan.operations)}), encoding="utf-8")
        os.replace(temporary, self.target)
        self.persist_calls += 1
        return ApplyReport(
            scene_id=plan.scene_id,
            changed_node_ids=tuple(dict.fromkeys(op.node_id for op in plan.operations)),
            destination_paths=plan.destination_paths,
        )


def _gate(tmp_path):
    target = tmp_path / "scene.json"
    target.write_text('{"revision":1}', encoding="utf-8")
    fingerprint = hashlib.sha256(target.read_bytes()).hexdigest()
    state = ApplyState(
        revision=2,
        operations=(EditOperation("door", EditKind.SET_POSITION, [1, 2, 3]),),
        baseline_view_ids=frozenset({"arrival", "close"}),
        final_view_ids=frozenset({"arrival", "close"}),
    )
    adapter = FixtureAdapter(target)
    artifacts = RunArtifacts(tmp_path / "run")
    return ApplyGate(adapter, "scene", fingerprint, state, artifacts), adapter, target


def test_apply_requires_latest_revision_comparison_and_approval(tmp_path) -> None:
    gate, adapter, _target = _gate(tmp_path)

    with pytest.raises(ApplyBlockedError, match="approval"):
        gate.apply(expected_revision=2, approval_note="")
    with pytest.raises(ApplyBlockedError, match="revision"):
        gate.apply(expected_revision=1, approval_note="approved")

    gate.state = replace(gate.state, final_view_ids=frozenset({"arrival"}))
    with pytest.raises(ApplyBlockedError, match="comparison"):
        gate.apply(expected_revision=2, approval_note="approved")

    assert adapter.persist_calls == 0


def test_source_conflict_preserves_original(tmp_path) -> None:
    gate, adapter, target = _gate(tmp_path)
    target.write_text('{"revision":99}', encoding="utf-8")

    with pytest.raises(SourceConflictError):
        gate.apply(2, "approved after review")

    assert target.read_text(encoding="utf-8") == '{"revision":99}'
    assert adapter.persist_calls == 0


def test_successful_apply_writes_report_after_adapter_persists(tmp_path) -> None:
    gate, adapter, target = _gate(tmp_path)

    report = gate.apply(2, "approved after comparing both views")

    assert adapter.persist_calls == 1
    assert json.loads(target.read_text(encoding="utf-8")) == {"applied": 1}
    artifact = json.loads(
        gate.artifacts.path("apply-report.json").read_text(encoding="utf-8")
    )
    assert artifact["approval_note"] == "approved after comparing both views"
    assert artifact["changed_node_ids"] == ["door"]
    assert report.changed_node_ids == ("door",)
    with pytest.raises(ApplyBlockedError, match="no preview changes"):
        gate.apply(2, "must not persist the same overlay twice")
    assert adapter.persist_calls == 1


def test_validation_failure_never_persists(tmp_path) -> None:
    gate, adapter, target = _gate(tmp_path)
    adapter.validate = lambda plan: ValidationReport(False, ("door intersects protected volume",))

    with pytest.raises(ApplyBlockedError, match="protected volume"):
        gate.apply(2, "approved")

    assert adapter.persist_calls == 0
    assert target.read_text(encoding="utf-8") == '{"revision":1}'
