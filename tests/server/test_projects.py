from __future__ import annotations

import json
import sys

import pytest

from illuminate.server.projects import ProjectConfigError, ProjectRegistry


def _write_registry(tmp_path, body: str):
    path = tmp_path / "projects.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_project_registry_loads_fixed_trusted_launch_values(tmp_path) -> None:
    cwd = tmp_path / "project"
    cwd.mkdir()
    path = _write_registry(
        tmp_path,
        f'''[projects.fixture]
python = {json.dumps(sys.executable)}
module = "fixture.workbench"
cwd = {json.dumps(str(cwd))}
scene_ids = ["triangle", "waystation"]

[projects.fixture.environment]
ILLUMINATE_STYLE = "test"
''',
    )

    project = ProjectRegistry.load(path).require("fixture")

    assert project.python == str(sys.executable)
    assert project.module == "fixture.workbench"
    assert project.cwd == cwd.resolve()
    assert project.scene_ids == frozenset({"triangle", "waystation"})
    assert project.environment == {"ILLUMINATE_STYLE": "test"}


def test_registry_rejects_unknown_fields_and_secret_environment(tmp_path) -> None:
    cwd = tmp_path / "project"
    cwd.mkdir()
    with pytest.raises(ProjectConfigError, match="unknown"):
        ProjectRegistry.load(
            _write_registry(
                tmp_path,
                f'''[projects.bad]
python = {json.dumps(sys.executable)}
module = "fixture.workbench"
cwd = {json.dumps(str(cwd))}
scene_ids = ["triangle"]
arguments = ["--caller-controlled"]
''',
            )
        )

    with pytest.raises(ProjectConfigError, match="secret"):
        ProjectRegistry.load(
            _write_registry(
                tmp_path,
                f'''[projects.bad]
python = {json.dumps(sys.executable)}
module = "fixture.workbench"
cwd = {json.dumps(str(cwd))}
scene_ids = ["triangle"]
[projects.bad.environment]
API_TOKEN = "must-not-be-configured"
''',
            )
        )


def test_registry_rejects_unregistered_project_and_scene(tmp_path) -> None:
    cwd = tmp_path / "project"
    cwd.mkdir()
    registry = ProjectRegistry.load(
        _write_registry(
            tmp_path,
            f'''[projects.fixture]
python = {json.dumps(sys.executable)}
module = "fixture.workbench"
cwd = {json.dumps(str(cwd))}
scene_ids = ["triangle"]
''',
        )
    )

    with pytest.raises(ProjectConfigError, match="not registered"):
        registry.require("other")
    with pytest.raises(ProjectConfigError, match="scene"):
        registry.require_scene("fixture", "caller-command")
