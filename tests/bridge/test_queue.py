from __future__ import annotations

import threading

import pytest

from illuminate.bridge.queue import CommandQueue, WrongThreadError
from illuminate.protocol import Operation, Request, Response


def request() -> Request:
    return Request(1, "r1", Operation.SCENE_SUMMARY, {})


def test_command_waits_until_owner_thread_pumps_it() -> None:
    queue = CommandQueue(owner_thread_id=threading.get_ident())
    submitted = queue.submit(request())

    assert not submitted.done()
    assert queue.pump(lambda item: Response.success(item.request_id, {"ok": 1})) == 1
    assert submitted.result().result == {"ok": 1}


def test_non_owner_thread_cannot_pump() -> None:
    queue = CommandQueue(owner_thread_id=threading.get_ident())
    errors: list[BaseException] = []

    def wrong_thread() -> None:
        try:
            queue.pump(lambda item: Response.success(item.request_id, {}))
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=wrong_thread)
    thread.start()
    thread.join()

    assert len(errors) == 1
    assert isinstance(errors[0], WrongThreadError)


def test_close_fails_pending_commands_and_is_idempotent() -> None:
    queue = CommandQueue(owner_thread_id=threading.get_ident())
    pending = queue.submit(request())

    queue.close()
    queue.close()

    with pytest.raises(RuntimeError, match="closed"):
        pending.result()
    with pytest.raises(RuntimeError, match="closed"):
        queue.submit(request())

