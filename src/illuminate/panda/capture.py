"""Canonical Panda3D camera captures with state restoration."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

from panda3d.core import Filename, PNMImage

from .registration import PandaSceneRegistration


_SAFE_VIEW_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


@dataclass(frozen=True)
class CameraView:
    view_id: str
    position: tuple[float, float, float]
    look_at: tuple[float, float, float]
    fov_degrees: float = 40.0


@dataclass(frozen=True)
class CaptureRecord:
    view_id: str
    path: Path
    width: int
    height: int
    sha256: str
    camera_position: tuple[float, float, float]
    look_at: tuple[float, float, float]


def capture_views(
    base,
    registration: PandaSceneRegistration,
    views: tuple[CameraView, ...],
    output_dir: Path,
) -> tuple[CaptureRecord, ...]:
    """Capture registered views and restore the workbench camera in all cases."""
    del registration  # Registration scopes the caller; captures never traverse globally.
    if base.win is None:
        raise RuntimeError("Panda3D has no graphics output for capture")
    for view in views:
        if not _SAFE_VIEW_ID.fullmatch(view.view_id) or ".." in view.view_id:
            raise ValueError(f"unsafe view id {view.view_id!r}")
    destination = output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    original_pos = base.camera.get_pos()
    original_hpr = base.camera.get_hpr()
    original_fov = base.camLens.get_fov()
    records: list[CaptureRecord] = []
    try:
        for view in views:
            base.camera.set_pos(*view.position)
            base.camera.look_at(*view.look_at)
            base.camLens.set_fov(view.fov_degrees)
            for _ in range(3):
                base.graphicsEngine.renderFrame()
            image = PNMImage()
            if not base.win.getScreenshot(image):
                raise RuntimeError(f"capture failed for view {view.view_id!r}")
            path = (destination / f"{view.view_id}.png").resolve()
            if path.parent != destination:
                raise ValueError("capture path escaped output directory")
            if not image.write(Filename.from_os_specific(str(path))):
                raise RuntimeError(f"could not write capture {path}")
            records.append(
                CaptureRecord(
                    view.view_id,
                    path,
                    image.get_x_size(),
                    image.get_y_size(),
                    sha256(path.read_bytes()).hexdigest(),
                    tuple(float(value) for value in view.position),
                    tuple(float(value) for value in view.look_at),
                )
            )
    finally:
        base.camera.set_pos(original_pos)
        base.camera.set_hpr(original_hpr)
        base.camLens.set_fov(original_fov)
    return tuple(records)

