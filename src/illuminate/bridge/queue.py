"""Owner-thread command queue used by the Panda bridge."""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass
from queue import Empty, Queue
import threading
from typing import Callable

from illuminate.protocol import Request, Response


class WrongThreadError(RuntimeError):
    pass


@dataclass(frozen=True)
class BridgeCommand:
    request: Request
    future: Future[Response]


class CommandQueue:
    def __init__(self, *, owner_thread_id: int) -> None:
        self._owner_thread_id = owner_thread_id
        self._commands: Queue[BridgeCommand] = Queue()
        self._closed = False
        self._lock = threading.Lock()

    def submit(self, request: Request) -> Future[Response]:
        future: Future[Response] = Future()
        with self._lock:
            if self._closed:
                raise RuntimeError("command queue is closed")
            self._commands.put(BridgeCommand(request, future))
        return future

    def pump(
        self,
        handler: Callable[[Request], Response],
        *,
        max_commands: int = 8,
    ) -> int:
        if threading.get_ident() != self._owner_thread_id:
            raise WrongThreadError("command queue must be pumped by its owner thread")
        if max_commands < 1:
            raise ValueError("max_commands must be positive")
        processed = 0
        while processed < max_commands:
            try:
                command = self._commands.get_nowait()
            except Empty:
                break
            if not command.future.cancelled():
                try:
                    command.future.set_result(handler(command.request))
                except BaseException as exc:
                    command.future.set_exception(exc)
            processed += 1
        return processed

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            while True:
                try:
                    command = self._commands.get_nowait()
                except Empty:
                    break
                if not command.future.done():
                    command.future.set_exception(RuntimeError("command queue is closed"))

