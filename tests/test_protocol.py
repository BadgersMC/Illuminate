import json

import pytest

from illuminate.protocol import (
    MAX_MESSAGE_BYTES,
    ErrorCode,
    Operation,
    ProtocolError,
    Request,
    Response,
    decode_request,
    encode_response,
)


def test_decodes_registered_request() -> None:
    request = decode_request(
        b'{"version":1,"id":"r1","operation":"scene_summary","payload":{}}'
    )

    assert request == Request(1, "r1", Operation.SCENE_SUMMARY, {})


def test_rejects_unknown_operation_and_top_level_fields() -> None:
    with pytest.raises(ProtocolError) as unknown:
        decode_request(b'{"version":1,"id":"r1","operation":"eval","payload":{}}')
    assert unknown.value.code is ErrorCode.UNKNOWN_OPERATION

    with pytest.raises(ProtocolError) as extra:
        decode_request(
            b'{"version":1,"id":"r1","operation":"scene_summary",'
            b'"payload":{},"token":"must-not-be-in-message"}'
        )
    assert extra.value.code is ErrorCode.INVALID_REQUEST


@pytest.mark.parametrize(
    "raw, code",
    (
        (b"not-json", ErrorCode.INVALID_JSON),
        (b"[]", ErrorCode.INVALID_REQUEST),
        (b'{"version":2,"id":"r1","operation":"scene_summary","payload":{}}', ErrorCode.UNSUPPORTED_VERSION),
        (b'{"version":1,"id":"r1","operation":"scene_summary","payload":[]}', ErrorCode.INVALID_REQUEST),
        (b'{"version":1,"id":"","operation":"scene_summary","payload":{}}', ErrorCode.INVALID_IDENTIFIER),
    ),
)
def test_rejects_malformed_requests_with_typed_error(raw: bytes, code: ErrorCode) -> None:
    with pytest.raises(ProtocolError) as error:
        decode_request(raw)
    assert error.value.code is code


def test_rejects_message_before_parsing_when_larger_than_limit() -> None:
    with pytest.raises(ProtocolError) as error:
        decode_request(b"{" + b" " * MAX_MESSAGE_BYTES + b"}")
    assert error.value.code is ErrorCode.MESSAGE_TOO_LARGE


def test_response_is_closed_and_contains_exactly_one_outcome() -> None:
    success = json.loads(encode_response(Response.success("r1", {"session_id": "s1"})))
    failure = json.loads(
        encode_response(Response.failure("r2", ErrorCode.INVALID_REQUEST, "bad"))
    )

    assert success == {
        "version": 1,
        "id": "r1",
        "ok": True,
        "result": {"session_id": "s1"},
    }
    assert failure == {
        "version": 1,
        "id": "r2",
        "ok": False,
        "error": {"code": "invalid_request", "message": "bad"},
    }


def test_response_encoding_does_not_invent_or_echo_a_secret() -> None:
    response = Response.success("r1", {"session_id": "s1"})
    encoded = encode_response(response)

    assert b"secret-token" not in encoded
    assert b"token" not in encoded

