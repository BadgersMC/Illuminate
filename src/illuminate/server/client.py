"""Synchronous client for the authenticated local bridge."""

from __future__ import annotations

import json
import socket
from typing import Mapping, Any
import uuid

from illuminate.bridge.transport import BridgeAddress, connect_and_handshake
from illuminate.protocol import (
    MAX_MESSAGE_BYTES,
    PROTOCOL_VERSION,
    ErrorCode,
    Operation,
    Response,
)


class BridgeClientError(ConnectionError):
    pass


class BridgeClient:
    def __init__(self, connection: socket.socket) -> None:
        self._connection = connection
        self._stream = connection.makefile("rb")
        self._closed = False

    @classmethod
    def connect(cls, address: BridgeAddress, token: str, *, timeout: float = 2.0) -> BridgeClient:
        return cls(connect_and_handshake(address, token, timeout=timeout))

    def request(
        self,
        operation: Operation,
        payload: Mapping[str, Any] | None = None,
    ) -> Response:
        if self._closed:
            raise BridgeClientError("bridge client is closed")
        request_id = uuid.uuid4().hex
        document = {
            "version": PROTOCOL_VERSION,
            "id": request_id,
            "operation": operation.value,
            "payload": dict(payload or {}),
        }
        encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_MESSAGE_BYTES:
            raise BridgeClientError("bridge request is too large")
        try:
            self._connection.sendall(encoded + b"\n")
            raw = self._stream.readline(MAX_MESSAGE_BYTES + 2)
        except OSError as exc:
            raise BridgeClientError("bridge request failed") from exc
        if not raw or not raw.endswith(b"\n") or len(raw) > MAX_MESSAGE_BYTES + 1:
            raise BridgeClientError("bridge response is missing or too large")
        try:
            decoded = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BridgeClientError("bridge returned invalid JSON") from exc
        if decoded.get("id") != request_id or decoded.get("version") != PROTOCOL_VERSION:
            raise BridgeClientError("bridge response does not match request")
        if decoded.get("ok") is True and isinstance(decoded.get("result"), dict):
            return Response.success(request_id, decoded["result"])
        error = decoded.get("error", {})
        try:
            code = ErrorCode(error.get("code"))
        except ValueError as exc:
            raise BridgeClientError("bridge returned an invalid error") from exc
        return Response.failure(request_id, code, str(error.get("message", "bridge error")))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._stream.close()
        finally:
            self._connection.close()
