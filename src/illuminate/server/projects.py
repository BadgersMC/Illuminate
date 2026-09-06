"""Strict trusted launch configuration."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import tomllib
from typing import Iterable, Mapping

from illuminate.protocol import MAX_IDENTIFIER_BYTES


class ProjectConfigError(ValueError):
    pass


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_MODULE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
_ENVIRONMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SECRET_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "PRIVATE_KEY")


@dataclass(frozen=True)
class ProjectConfig:
    project_id: str
    python: str
    module: str
    cwd: Path
    scene_ids: frozenset[str]
    environment: Mapping[str, str]

    def __post_init__(self) -> None:
        _validate_identifier(self.project_id, "project id")
        if not isinstance(self.python, str) or not self.python:
            raise ProjectConfigError("python executable is required")
        if not _MODULE.fullmatch(self.module):
            raise ProjectConfigError("module must be a dotted Python module name")
        resolved_cwd = Path(self.cwd).resolve()
        if not resolved_cwd.is_dir():
            raise ProjectConfigError("project cwd must be an existing directory")
        object.__setattr__(self, "cwd", resolved_cwd)
        if not self.scene_ids:
            raise ProjectConfigError("project must register at least one scene")
        for scene_id in self.scene_ids:
            _validate_identifier(scene_id, "scene id")
        checked_environment: dict[str, str] = {}
        for key, value in self.environment.items():
            if not _ENVIRONMENT.fullmatch(key):
                raise ProjectConfigError(f"invalid environment key {key!r}")
            if any(marker in key.upper() for marker in _SECRET_MARKERS):
                raise ProjectConfigError("secret environment keys are not allowed")
            if not isinstance(value, str):
                raise ProjectConfigError("environment values must be strings")
            checked_environment[key] = value
        object.__setattr__(self, "environment", checked_environment)


class ProjectRegistry:
    def __init__(self, projects: Iterable[ProjectConfig]) -> None:
        indexed: dict[str, ProjectConfig] = {}
        for project in projects:
            if project.project_id in indexed:
                raise ProjectConfigError(f"duplicate project {project.project_id!r}")
            indexed[project.project_id] = project
        if not indexed:
            raise ProjectConfigError("registry contains no projects")
        self._projects = indexed

    @classmethod
    def load(cls, path: Path | str) -> ProjectRegistry:
        config_path = Path(path).resolve()
        try:
            document = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ProjectConfigError(f"could not load project registry: {exc}") from exc
        if set(document) != {"projects"} or not isinstance(document["projects"], dict):
            raise ProjectConfigError("registry must contain only a projects table")
        projects: list[ProjectConfig] = []
        for project_id, raw in document["projects"].items():
            if not isinstance(raw, dict):
                raise ProjectConfigError(f"project {project_id!r} must be a table")
            allowed = {"python", "module", "cwd", "scene_ids", "environment"}
            unknown = set(raw) - allowed
            missing = {"python", "module", "cwd", "scene_ids"} - set(raw)
            if unknown:
                raise ProjectConfigError(f"unknown project fields: {sorted(unknown)}")
            if missing:
                raise ProjectConfigError(f"missing project fields: {sorted(missing)}")
            scenes = raw["scene_ids"]
            environment = raw.get("environment", {})
            if not isinstance(scenes, list) or not all(isinstance(item, str) for item in scenes):
                raise ProjectConfigError("scene_ids must be an array of strings")
            if not isinstance(environment, dict):
                raise ProjectConfigError("environment must be a table")
            projects.append(
                ProjectConfig(
                    project_id=project_id,
                    python=raw["python"],
                    module=raw["module"],
                    cwd=Path(raw["cwd"]),
                    scene_ids=frozenset(scenes),
                    environment=environment,
                )
            )
        return cls(projects)

    def require(self, project_id: str) -> ProjectConfig:
        try:
            return self._projects[project_id]
        except KeyError as exc:
            raise ProjectConfigError(f"project {project_id!r} is not registered") from exc

    def require_scene(self, project_id: str, scene_id: str) -> ProjectConfig:
        project = self.require(project_id)
        if scene_id not in project.scene_ids:
            raise ProjectConfigError(
                f"scene {scene_id!r} is not registered for project {project_id!r}"
            )
        return project


def _validate_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ProjectConfigError(f"{label} has an invalid format")
    if len(value.encode("utf-8")) > MAX_IDENTIFIER_BYTES:
        raise ProjectConfigError(f"{label} is too long")
    return value
