from __future__ import annotations

import json
import threading
import time

from panda3d.core import load_prc_file_data

from illuminate.bridge.runtime import IlluminateBridge
from illuminate.bridge.transport import connect_and_handshake
from illuminate.core.scene import SceneRegistry
from illuminate.protocol import Response


load_prc_file_data("", "window-type none\naudio-library-name null")


class SummaryAdapter:
    def dispatch(self, request, registry):
        return Response.success(request.request_id, registry.summary(depth=1))


def test_headless_bridge_dispatches_on_panda_thread_and_cleans_up() -> None:
    from direct.showbase.ShowBase import ShowBase

    base = ShowBase(windowType="none")
    registry = SceneRegistry("triangle")
    registry.register("root", None, "root", frozenset(), base.render)
    bridge = IlluminateBridge.attach(
        base,
        registry,
        SummaryAdapter(),
        token="correct",
    )
    result: list[dict[str, object]] = []

    def client() -> None:
        connection = connect_and_handshake(bridge.address, "correct")
        try:
            connection.sendall(
                b'{"version":1,"id":"r1","operation":"scene_summary","payload":{}}\n'
            )
            data = b""
            while not data.endswith(b"\n"):
                data += connection.recv(4096)
            result.append(json.loads(data))
        finally:
            connection.close()

    thread = threading.Thread(target=client)
    thread.start()
    deadline = time.monotonic() + 2.0
    while not result and time.monotonic() < deadline:
        base.task_mgr.step()
        time.sleep(0.005)

    task_name = bridge.task_name
    bridge.close()
    bridge.close()
    thread.join(timeout=1.0)

    assert result[0]["result"]["scene_id"] == "triangle"
    assert not base.task_mgr.hasTaskNamed(task_name)
    base.destroy()

