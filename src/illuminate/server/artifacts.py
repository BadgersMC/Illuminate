"""Contained, atomic artifacts for one Illuminate run."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
from typing import Any, Iterable


class ArtifactPathError(ValueError):
    pass


class RunArtifacts:
    MARKER = ".illuminate-run.json"

    def __init__(
        self,
        root: Path | str,
        *,
        secrets: Iterable[str] = (),
        _newly_created: bool = False,
    ) -> None:
        self.root = Path(root).resolve()
        self._secrets = frozenset(value for value in secrets if value)
        if self.root.exists():
            if not self.root.is_dir():
                raise ArtifactPathError("run root is not a directory")
            entries = list(self.root.iterdir())
            if not (self.root / self.MARKER).is_file() and not (
                _newly_created and not entries
            ):
                raise ArtifactPathError("existing directory is not an Illuminate run")
        else:
            self.root.mkdir(parents=True)
        marker = self.root / self.MARKER
        if not marker.exists():
            self._atomic_json(
                marker,
                {
                    "format": "illuminate-run",
                    "version": 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )

    @classmethod
    def create_unique(cls, parent: Path | str, *, secrets: Iterable[str] = ()) -> RunArtifacts:
        parent_path = Path(parent).resolve()
        parent_path.mkdir(parents=True, exist_ok=True)
        for _attempt in range(32):
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            candidate = parent_path / f"run-{timestamp}-{secrets_module_token()}"
            try:
                candidate.mkdir()
            except FileExistsError:
                continue
            return cls(candidate, secrets=secrets, _newly_created=True)
        raise ArtifactPathError("could not allocate a unique run directory")

    def path(self, relative: Path | str) -> Path:
        candidate_input = Path(relative)
        if candidate_input.is_absolute():
            raise ArtifactPathError("artifact path must be relative to the run root")
        candidate = (self.root / candidate_input).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ArtifactPathError("artifact path escapes the run root") from exc
        if candidate == self.root:
            raise ArtifactPathError("artifact path must name a file")
        return candidate

    def write_json(self, relative: Path | str, document: Any) -> Path:
        encoded = json.dumps(document, ensure_ascii=False, sort_keys=True)
        lowered = encoded.lower()
        if any(secret in encoded for secret in self._secrets):
            raise ArtifactPathError("artifact contains a registered secret")
        if any(f'"{name}"' in lowered for name in ("token", "secret", "password", "credential")):
            raise ArtifactPathError("artifact contains a secret-bearing field")
        destination = self.path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_text(destination, encoded + "\n")
        return destination

    @staticmethod
    def _atomic_json(path: Path, document: Any) -> None:
        RunArtifacts._atomic_text(
            path,
            json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n",
        )

    @staticmethod
    def _atomic_text(path: Path, text: str) -> None:
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
        try:
            temporary.write_text(text, encoding="utf-8")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def secrets_module_token() -> str:
    """Return a short collision-resistant suffix without shadowing constructor input."""
    return secrets.token_hex(4)
