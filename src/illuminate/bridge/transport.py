"""Single-controller authenticated JSON transport bound to loopback."""

from __future__ import annotations

from dataclasses import dataclass
import json
import socket
import threading
from typing import BinaryIO, Callable

from illuminate.protocol import (
    MAX_MESSAGE_BYTES,
    ErrorCode,
    ProtocolError,
    Request,
    Response,
    decode_request,
    encode_response,
)


class AuthenticationError(ConnectionError):
    pass


class ConnectionBusyError(ConnectionError):
    pass


@dataclass(frozen=True)
class BridgeAddress:
    host: str
    port: int


def _read_line(stream: BinaryIO, limit: int) -> bytes | None:
    line = stream.readline(limit + 2)
    if line == b"":
        return None
    if len(line) > limit + 1 or not line.endswith(b"\n"):
        raise ProtocolError(ErrorCode.MESSAGE_TOO_LARGE, f"message exceeds {limit} bytes")
    return line[:-1]


def _handshake_error(connection: socket.socket, code: str, message: str) -> None:
    document = {"ok": False, "error": {"code": code, "message": message}}
    connection.sendall(json.dumps(document, separators=(",", ":")).encode() + b"\n")


class LoopbackBridgeServer:
    def __init__(
        self,
        *,
        token: str,
        handler: Callable[[Request], Response],
        port: int = 0,
        handshake_timeout: float = 2.0,
    ) -> None:
        if not token:
            raise ValueError("token is required")
        self._token = token
        self._handler = handler
        self._requested_port = port
        self._handshake_timeout = handshake_timeout
        self._listener: socket.socket | None = None
        self._client: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._client_threads: list[threading.Thread] = []
        self._closed = threading.Event()
        self._state_lock = threading.Lock()
        self._controller_reserved = False
        self._address: BridgeAddress | None = None

    def __repr__(self) -> str:
        return f"LoopbackBridgeServer(address={self._address!r}, closed={self._closed.is_set()})"

    @property
    def address(self) -> BridgeAddress:
        if self._address is None:
            raise RuntimeError("bridge server has not started")
        return self._address

    def start(self) -> None:
        if self._listener is not None:
            return
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", self._requested_port))
        listener.listen(4)
        listener.settimeout(0.1)
        self._listener = listener
        host, port = listener.getsockname()
        self._address = BridgeAddress(str(host), int(port))
        self._accept_thread = threading.Thread(
            target=self._accept_loop,
            name="illuminate-bridge-accept",
            daemon=True,
        )
        self._accept_thread.start()

    def _accept_loop(self) -> None:
        assert self._listener is not None
        while not self._closed.is_set():
            try:
                connection, _peer = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            with self._state_lock:
                if self._controller_reserved:
                    try:
                        connection.settimeout(0.25)
                        busy_stream = connection.makefile("rb")
                        try:
                            _read_line(busy_stream, 4096)
                        finally:
                            busy_stream.close()
                        _handshake_error(
                            connection,
                            "connection_busy",
                            "controller already connected",
                        )
                        connection.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                    finally:
                        connection.close()
                    continue
                self._controller_reserved = True
                self._client = connection
            thread = threading.Thread(
                target=self._serve_connection,
                args=(connection,),
                name="illuminate-bridge-client",
                daemon=True,
            )
            self._client_threads.append(thread)
            thread.start()

    def _serve_connection(self, connection: socket.socket) -> None:
        try:
            connection.settimeout(self._handshake_timeout)
            stream = connection.makefile("rb")
            try:
                raw_handshake = _read_line(stream, 4096)
                try:
                    handshake = json.loads(raw_handshake or b"")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    handshake = None
                if handshake != {"token": self._token}:
                    _handshake_error(connection, "authentication_failed", "authentication failed")
                    return
                connection.sendall(b'{"ok":true}\n')
                connection.settimeout(None)
                while not self._closed.is_set():
                    try:
                        raw = _read_line(stream, MAX_MESSAGE_BYTES)
                    except ProtocolError as exc:
                        connection.sendall(
                            encode_response(Response.failure("protocol", exc.code, str(exc))) + b"\n"
                        )
                        return
                    if raw is None:
                        return
                    try:
                        request = decode_request(raw)
                        response = self._handler(request)
                    except ProtocolError as exc:
                        response = Response.failure("protocol", exc.code, str(exc))
                    except BaseException:
                        response = Response.failure(
                            "protocol", ErrorCode.INTERNAL_ERROR, "bridge handler failed"
                        )
                    connection.sendall(encode_response(response) + b"\n")
            finally:
                stream.close()
        except (OSError, TimeoutError):
            return
        finally:
            try:
                connection.close()
            finally:
                with self._state_lock:
                    if self._client is connection:
                        self._client = None
                    self._controller_reserved = False

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        listener, self._listener = self._listener, None
        if listener is not None:
            listener.close()
        with self._state_lock:
            client = self._client
        if client is not None:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client.close()
        current = threading.current_thread()
        if self._accept_thread is not None and self._accept_thread is not current:
            self._accept_thread.join(timeout=1.0)
        for thread in self._client_threads:
            if thread is not current:
                thread.join(timeout=1.0)


def connect_and_handshake(
    address: BridgeAddress,
    token: str,
    *,
    timeout: float = 2.0,
) -> socket.socket:
    connection = socket.create_connection((address.host, address.port), timeout=timeout)
    connection.sendall(
        json.dumps({"token": token}, separators=(",", ":")).encode() + b"\n"
    )
    stream = connection.makefile("rb")
    try:
        raw = _read_line(stream, 4096)
    finally:
        stream.close()
    try:
        response = json.loads(raw or b"")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        connection.close()
        raise AuthenticationError("invalid bridge handshake response") from exc
    if response.get("ok") is not True:
        connection.close()
        code = response.get("error", {}).get("code")
        if code == "connection_busy":
            raise ConnectionBusyError("bridge already has a controller")
        raise AuthenticationError("bridge authentication failed")
    connection.settimeout(timeout)
    return connection
