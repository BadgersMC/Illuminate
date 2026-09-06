from __future__ import annotations

from panda3d.core import AmbientLight, CardMaker, LColor, load_prc_file_data

from illuminate.panda.capture import CameraView, capture_views
from illuminate.panda.registration import PandaSceneRegistration


load_prc_file_data(
    "",
    "\n".join(
        (
            "window-type offscreen",
            "win-size 320 180",
            "audio-library-name null",
            "framebuffer-multisample false",
            "multisamples 0",
        )
    ),
)


def test_capture_writes_image_metadata_and_restores_camera(tmp_path) -> None:
    from direct.showbase.ShowBase import ShowBase

    base = ShowBase(windowType="offscreen")
    try:
        base.set_background_color(0.05, 0.08, 0.12, 1.0)
        maker = CardMaker("subject")
        maker.set_frame(-1.5, 1.5, -1.0, 1.0)
        subject = base.render.attach_new_node(maker.generate())
        subject.set_pos(0, 4, 1.2)
        subject.set_color(0.9, 0.45, 0.1, 1)
        subject.set_light_off(1)
        registration = PandaSceneRegistration("fixture")
        registration.add_node("root", base.render, frozenset())
        registration.add_node("subject", subject, frozenset(), parent_id="root")
        base.camera.set_pos(7, -3, 5)
        base.camera.set_hpr(12, -8, 0)
        original_pos = tuple(base.camera.get_pos())
        original_hpr = tuple(base.camera.get_hpr())

        records = capture_views(
            base,
            registration,
            (CameraView("arrival", (0, -8, 3), (0, 4, 1)),),
            tmp_path,
        )

        assert len(records) == 1
        assert records[0].path == (tmp_path / "arrival.png").resolve()
        assert records[0].path.exists()
        assert records[0].width == 320
        assert records[0].height == 180
        assert len(records[0].sha256) == 64
        assert records[0].camera_position == (0.0, -8.0, 3.0)
        assert tuple(base.camera.get_pos()) == original_pos
        assert tuple(base.camera.get_hpr()) == original_hpr
    finally:
        base.destroy()


def test_capture_rejects_unknown_view_id_before_render(tmp_path) -> None:
    from direct.showbase.ShowBase import ShowBase

    base = ShowBase(windowType="offscreen")
    try:
        registration = PandaSceneRegistration("fixture")
        registration.add_node("root", base.render, frozenset())
        try:
            capture_views(
                base,
                registration,
                (CameraView("../escape", (0, -8, 3), (0, 0, 0)),),
                tmp_path,
            )
        except ValueError as error:
            assert "view id" in str(error)
        else:
            raise AssertionError("unsafe view id was accepted")
        assert list(tmp_path.iterdir()) == []
    finally:
        base.destroy()

