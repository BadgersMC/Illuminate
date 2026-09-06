from __future__ import annotations

import json
import socket

import pytest

from illuminate.bridge.transport import (
    AuthenticationError,
    ConnectionBusyError,
    LoopbackBridgeServer,
    connect_and_handshake,
)
from illuminate.protocol import ErrorCode, Response


def receive_line(connection: socket.socket) -> dict[str, object]:
    buffer = b""
    while not buffer.endswith(b"\n"):
        buffer += connection.recv(4096)
    return json.loads(buffer)


def test_bridge_binds_loopback_and_rejects_bad_token() -> None:
    server = LoopbackBridgeServer(
        token="correct",
        handler=lambda request: Response.success(request.request_id, {}),
    )
    server.start()
    try:
        assert server.address.host == "127.0.0.1"
        with pytest.raises(AuthenticationError):
            connect_and_handshake(server.address, "wrong")
    finally:
        server.close()


def test_authenticated_controller_can_exchange_one_request() -> None:
    server = LoopbackBridgeServer(
        token="correct",
        handler=lambda request: Response.success(
            request.request_id,
            {"operation": request.operation.value},
        ),
    )
    server.start()
    connection = connect_and_handshake(server.address, "correct")
    try:
        connection.sendall(
            b'{"version":1,"id":"r1","operation":"scene_summary","payload":{}}\n'
        )
        assert receive_line(connection) == {
            "version": 1,
            "id": "r1",
            "ok": True,
            "result": {"operation": "scene_summary"},
        }
    finally:
        connection.close()
        server.close()


def test_second_controller_is_rejected_while_first_is_connected() -> None:
    server = LoopbackBridgeServer(
        token="correct",
        handler=lambda request: Response.success(request.request_id, {}),
    )
    server.start()
    first = connect_and_handshake(server.address, "correct")
    try:
        with pytest.raises(ConnectionBusyError):
            connect_and_handshake(server.address, "correct")
    finally:
        first.close()
        server.close()


def test_oversized_frame_is_rejected_without_dispatch() -> None:
    calls = []
    server = LoopbackBridgeServer(
        token="correct",
        handler=lambda request: calls.append(request),
    )
    server.start()
    connection = connect_and_handshake(server.address, "correct")
    try:
        connection.sendall(b"{" + b" " * (1024 * 1024) + b"}\n")
        response = receive_line(connection)
        assert response["error"]["code"] == ErrorCode.MESSAGE_TOO_LARGE.value
        assert calls == []
    finally:
        connection.close()
        server.close()


def test_token_is_absent_from_server_representation() -> None:
    server = LoopbackBridgeServer(token="secret-token", handler=lambda request: None)
    assert "secret-token" not in repr(server)

