"""Panda3D-owned lifecycle for the Illuminate bridge."""

from __future__ import annotations

from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, Protocol

from direct.task import Task

from illuminate.core.scene import SceneRegistry
from illuminate.protocol import ErrorCode, Request, Response

from .queue import CommandQueue
from .transport import BridgeAddress, LoopbackBridgeServer


class BridgeAdapter(Protocol):
    def dispatch(self, request: Request, registry: SceneRegistry) -> Response: ...


class IlluminateBridge:
    def __init__(
        self,
        base: Any,
        registry: SceneRegistry,
        adapter: BridgeAdapter,
        *,
        token: str,
        port: int,
    ) -> None:
        import threading

        self._base = base
        self._registry = registry
        self._adapter = adapter
        self._queue = CommandQueue(owner_thread_id=threading.get_ident())
        self._closed = False
        self.task_name = f"illuminate-bridge-pump-{id(self)}"
        self._server = LoopbackBridgeServer(
            token=token,
            handler=self._submit_from_transport,
            port=port,
        )
        self._server.start()
        self._base.task_mgr.add(self._task, self.task_name)

    @classmethod
    def attach(
        cls,
        base: Any,
        registry: SceneRegistry,
        adapter: BridgeAdapter,
        *,
        token: str,
        port: int = 0,
    ) -> IlluminateBridge:
        return cls(base, registry, adapter, token=token, port=port)

    @property
    def address(self) -> BridgeAddress:
        return self._server.address

    def _submit_from_transport(self, request: Request) -> Response:
        try:
            return self._queue.submit(request).result(timeout=5.0)
        except FutureTimeoutError:
            return Response.failure(request.request_id, ErrorCode.INTERNAL_ERROR, "command timed out")
        except BaseException:
            return Response.failure(request.request_id, ErrorCode.INTERNAL_ERROR, "command failed")

    def pump(self, *, max_commands: int = 8) -> int:
        return self._queue.pump(
            lambda request: self._adapter.dispatch(request, self._registry),
            max_commands=max_commands,
        )

    def _task(self, task: Task.Task) -> int:
        self.pump()
        return Task.cont

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.close()
        self._server.close()
        self._base.task_mgr.remove(self.task_name)

