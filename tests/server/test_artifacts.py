from __future__ import annotations

import json

import pytest

from illuminate.server.artifacts import ArtifactPathError, RunArtifacts


def test_run_artifacts_reject_paths_outside_run_root(tmp_path) -> None:
    artifacts = RunArtifacts(tmp_path / "run")

    with pytest.raises(ArtifactPathError):
        artifacts.path("../escape.json")
    with pytest.raises(ArtifactPathError):
        artifacts.path(tmp_path / "absolute.json")


def test_json_write_is_atomic_and_rejects_secrets(tmp_path) -> None:
    artifacts = RunArtifacts(tmp_path / "run", secrets={"session-secret"})
    output = artifacts.write_json("state/summary.json", {"scene": "triangle"})

    assert json.loads(output.read_text(encoding="utf-8")) == {"scene": "triangle"}
    assert not list(output.parent.glob("*.tmp"))
    with pytest.raises(ArtifactPathError, match="secret"):
        artifacts.write_json("leak.json", {"value": "session-secret"})


def test_existing_non_run_directory_is_not_adopted(tmp_path) -> None:
    directory = tmp_path / "notes"
    directory.mkdir()
    (directory / "keep.txt").write_text("user data", encoding="utf-8")

    with pytest.raises(ArtifactPathError, match="not an Illuminate run"):
        RunArtifacts(directory)

    empty_directory = tmp_path / "empty"
    empty_directory.mkdir()
    with pytest.raises(ArtifactPathError, match="not an Illuminate run"):
        RunArtifacts(empty_directory)


def test_create_unique_never_reuses_a_run_directory(tmp_path) -> None:
    first = RunArtifacts.create_unique(tmp_path)
    second = RunArtifacts.create_unique(tmp_path)

    assert first.root != second.root
    assert first.root.parent == second.root.parent == tmp_path.resolve()
