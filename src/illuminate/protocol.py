"""Closed, versioned messages shared by the Illuminate server and bridge."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any, Mapping


PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 1024 * 1024
MAX_IDENTIFIER_BYTES = 128


class Operation(Enum):
    LAUNCH_SCENE = "launch_scene"
    SCENE_SUMMARY = "scene_summary"
    INSPECT_NODES = "inspect_nodes"
    PREVIEW_CHANGES = "preview_changes"
    CAPTURE_VIEWS = "capture_views"
    UNDO_CHANGES = "undo_changes"
    APPLY_CHANGES = "apply_changes"
    CLOSE_SCENE = "close_scene"


class ErrorCode(Enum):
    INVALID_JSON = "invalid_json"
    INVALID_REQUEST = "invalid_request"
    MESSAGE_TOO_LARGE = "message_too_large"
    INVALID_IDENTIFIER = "invalid_identifier"
    UNSUPPORTED_VERSION = "unsupported_version"
    UNKNOWN_OPERATION = "unknown_operation"
    EDIT_REJECTED = "edit_rejected"
    REVISION_CONFLICT = "revision_conflict"
    INTERNAL_ERROR = "internal_error"


class ProtocolError(ValueError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Request:
    version: int
    request_id: str
    operation: Operation
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class Response:
    request_id: str
    ok: bool
    result: Mapping[str, Any] | None = None
    error_code: ErrorCode | None = None
    error_message: str | None = None

    @classmethod
    def success(cls, request_id: str, result: Mapping[str, Any]) -> Response:
        _validate_identifier(request_id, "response id")
        return cls(request_id=request_id, ok=True, result=dict(result))

    @classmethod
    def failure(
        cls,
        request_id: str,
        code: ErrorCode,
        message: str,
    ) -> Response:
        _validate_identifier(request_id, "response id")
        return cls(
            request_id=request_id,
            ok=False,
            error_code=code,
            error_message=message,
        )


def _validate_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProtocolError(ErrorCode.INVALID_IDENTIFIER, f"{label} is required")
    if len(value.encode("utf-8")) > MAX_IDENTIFIER_BYTES:
        raise ProtocolError(
            ErrorCode.INVALID_IDENTIFIER,
            f"{label} exceeds {MAX_IDENTIFIER_BYTES} UTF-8 bytes",
        )
    return value


def decode_request(raw: bytes) -> Request:
    """Decode one bounded JSON request without accepting schema extensions."""
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError(
            ErrorCode.MESSAGE_TOO_LARGE,
            f"message exceeds {MAX_MESSAGE_BYTES} bytes",
        )
    try:
        decoded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(ErrorCode.INVALID_JSON, "message is not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise ProtocolError(ErrorCode.INVALID_REQUEST, "request must be a JSON object")
    required = {"version", "id", "operation", "payload"}
    if set(decoded) != required:
        raise ProtocolError(
            ErrorCode.INVALID_REQUEST,
            "request fields must be version, id, operation, and payload",
        )
    version = decoded["version"]
    if type(version) is not int or version != PROTOCOL_VERSION:
        raise ProtocolError(
            ErrorCode.UNSUPPORTED_VERSION,
            f"protocol version must be {PROTOCOL_VERSION}",
        )
    request_id = _validate_identifier(decoded["id"], "request id")
    if not isinstance(decoded["payload"], dict):
        raise ProtocolError(ErrorCode.INVALID_REQUEST, "payload must be an object")
    try:
        operation = Operation(decoded["operation"])
    except (TypeError, ValueError) as exc:
        raise ProtocolError(ErrorCode.UNKNOWN_OPERATION, "operation is not registered") from exc
    return Request(version, request_id, operation, decoded["payload"])


def encode_response(response: Response) -> bytes:
    """Encode one response with exactly one success or failure outcome."""
    _validate_identifier(response.request_id, "response id")
    if response.ok:
        if response.result is None or response.error_code is not None:
            raise ProtocolError(ErrorCode.INVALID_REQUEST, "invalid success response")
        document: dict[str, Any] = {
            "version": PROTOCOL_VERSION,
            "id": response.request_id,
            "ok": True,
            "result": dict(response.result),
        }
    else:
        if response.error_code is None or response.error_message is None or response.result is not None:
            raise ProtocolError(ErrorCode.INVALID_REQUEST, "invalid failure response")
        document = {
            "version": PROTOCOL_VERSION,
            "id": response.request_id,
            "ok": False,
            "error": {
                "code": response.error_code.value,
                "message": response.error_message,
            },
        }
    return json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
