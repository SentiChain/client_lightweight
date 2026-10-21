"""Public matrices, proof limitations and purchase transport contract."""

import copy
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding

from sentichain import (
    APIError,
    AuthenticationError,
    Client,
    InsufficientCreditsError,
    ResponseError,
    TransportError,
    keys,
    verify_matrix_signature,
    verify_signature,
)

BLOCK = {
    "block_number": 7,
    "block_timestamp": 1792455038.5,
    "hash": "canonical-block-hash",
    "transactions": [{"post_matrix": [[0.1, -0.2], [0.3, 0.4], [0.5, -0.6]]}],
}


def response(payload, status=200, headers=None):
    result = requests.Response()
    result.status_code = status
    result.headers.update(headers or {})
    result._content = json.dumps(payload).encode()
    result._content_consumed = True
    return result


@pytest.fixture
def session(monkeypatch):
    result = Mock(spec=requests.Session)
    monkeypatch.setattr("sentichain.client.requests.Session", lambda: result)
    return result


def test_paid_retry_reuses_uuid_and_new_purchase_has_new_uuid(session):
    session.get.side_effect = [
        requests.Timeout("credential must never escape"),
        response({"block": BLOCK}),
        response({"block": BLOCK}),
    ]
    with Client(api_key="ytk_test", max_retries=1, backoff_factor=0) as client:
        assert client.get_last_block("mainnet") == BLOCK
        first = client.last_operation_id
        assert str(UUID(first)) == first
        assert client.get_last_block("mainnet") == BLOCK
        assert client.last_operation_id != first
    sent = [call.kwargs["headers"]["Idempotency-Key"] for call in session.get.call_args_list]
    assert sent[0] == sent[1] == first
    assert sent[2] != first


def test_uncertain_transport_exposes_uuid_for_explicit_same_purchase_retry(session):
    session.get.side_effect = requests.ConnectionError("private server detail")
    with Client(api_key="ytk_test", max_retries=0) as client:
        with pytest.raises(TransportError) as caught:
            client.get_last_block("mainnet")
        operation = caught.value.operation_id
        assert operation == client.last_operation_id
        session.get.side_effect = None
        session.get.return_value = response({"block": BLOCK})
        client.get_last_block("mainnet", idempotency_key=operation)
        assert session.get.call_args.kwargs["headers"]["Idempotency-Key"] == operation


@pytest.mark.parametrize("value", ["not-a-uuid", 123, "", str(uuid4()).replace("-", "")])
def test_invalid_idempotency_uuid_rejected_before_transport(session, value):
    with Client(api_key="ytk_test") as client:
        with pytest.raises(ValueError, match="UUID"):
            client.get_last_block("mainnet", idempotency_key=value)
    session.get.assert_not_called()


def test_key_required_for_paid_reads_but_free_metadata_has_no_credentials(session):
    with Client(max_retries=0) as client:
        with pytest.raises(AuthenticationError):
            client.get_last_block("mainnet")
        session.get.assert_not_called()
        session.get.return_value = response({"chain_length": 8})
        assert client.get_chain_length("mainnet") == 8
        assert session.get.call_args.kwargs["headers"] == {}


def test_credit_receipt_and_sanitized_insufficient_balance(session):
    session.get.side_effect = [
        response(
            {"block": BLOCK},
            headers={"X-Yototec-Credits-Charged": "1", "X-Yototec-Credits-Remaining": "999"},
        ),
        response(
            {
                "error": {
                    "code": "insufficient_credits",
                    "message": "private raw source",
                    "required_credits": 1,
                    "available_credits": 0,
                }
            },
            status=402,
        ),
    ]
    with Client(api_key="ytk_test", max_retries=0) as client:
        client.get_last_block("mainnet")
        assert client.credits_charged == 1
        assert client.credits_remaining == 999
        with pytest.raises(InsufficientCreditsError) as caught:
            client.get_last_block("mainnet")
        assert caught.value.required_credits == 1
        assert caught.value.available_credits == 0
        assert caught.value.operation_id == client.last_operation_id
        assert client.credits_charged is None
        assert client.credits_remaining is None
        assert "raw source" not in str(caught.value)
    assert session.get.call_count == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"error": {"required_credits": True, "available_credits": -1}},
        {"error": ["private"]},
        ["private"],
        None,
    ],
)
def test_malformed_insufficient_payload_does_not_leak(session, payload):
    session.get.return_value = response(payload, status=402)
    with Client(api_key="ytk_test", max_retries=0) as client:
        with pytest.raises(InsufficientCreditsError) as caught:
            client.get_last_block("mainnet")
        assert caught.value.required_credits is None
        assert caught.value.available_credits is None


@pytest.mark.parametrize(
    "forbidden",
    [
        "source",
        "post_link",
        "post_timestamp",
        "transaction_timestamp",
        "sender",
        "nonce",
        "public_key",
        "signature",
        "source_id",
        "url",
        "extra",
    ],
)
def test_public_reader_rejects_source_or_unapproved_transaction_fields(session, forbidden):
    block = copy.deepcopy(BLOCK)
    block["transactions"][0][forbidden] = "original source text https://x.com/test/status/123"
    session.get.return_value = response({"block": block})
    with Client(api_key="ytk_test", max_retries=0) as client:
        with pytest.raises(ResponseError) as caught:
            client.get_last_block("mainnet")
    assert "original source" not in str(caught.value)
    assert "x.com" not in str(caught.value)


@pytest.mark.parametrize(
    "matrix", [[], [[]], [[1], [2, 3]], [[True]], [["source"]], [[float("nan")]]]
)
def test_malformed_matrix_is_rejected(session, matrix):
    block = copy.deepcopy(BLOCK)
    block["transactions"][0]["post_matrix"] = matrix
    session.get.return_value = response({"block": block})
    with Client(api_key="ytk_test", max_retries=0) as client:
        with pytest.raises(ResponseError):
            client.get_last_block("mainnet")


def test_full_ordered_matrix_is_preserved_and_not_a_signed_transaction(session):
    block = copy.deepcopy(BLOCK)
    block["transactions"].append({"post_matrix": [[0.9, 0.8], [0.7, 0.6]]})
    before = copy.deepcopy(block)
    session.get.return_value = response({"block": block})
    with Client(api_key="ytk_test") as client:
        public = client.get_block_by_number("mainnet", 7)
    assert public == before
    assert [len(row["post_matrix"]) for row in public["transactions"]] == [3, 2]
    assert public["transactions"][0]["post_matrix"][2] == [0.5, -0.6]
    assert not verify_signature(json.dumps(public["transactions"][0]))


def test_read_methods_for_retired_surfaces_are_removed():
    for name in (
        "get_user_info",
        "get_points_by_block_no_embedding",
        "get_points_by_block_range_no_embedding",
        "get_reasoning_match_chunk_end",
    ):
        assert not hasattr(Client, name)


def test_matrix_proof_authenticates_exact_values_and_trusted_key_only():
    private, public = keys.generate_key_pair()
    other_private, other_public = keys.generate_key_pair()
    matrix = BLOCK["transactions"][0]["post_matrix"]
    signature = private.sign(
        json.dumps(matrix).encode("utf-8"),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    ).hex()
    assert verify_matrix_signature(matrix, signature, public)
    changed = copy.deepcopy(matrix)
    changed[2][1] = -0.61
    assert not verify_matrix_signature(changed, signature, public)
    assert not verify_matrix_signature(matrix[:1], signature, public)
    assert not verify_matrix_signature(matrix, signature, other_public)
    assert not verify_matrix_signature(matrix, "invalid hex", public)
    assert not verify_matrix_signature([], signature, public)
    assert not verify_matrix_signature(matrix, signature, ec.generate_private_key(ec.SECP256R1()))
    assert not verify_matrix_signature(matrix, 42, public)
    del other_private


def test_real_local_http_retry_debits_once_and_metadata_is_free():
    """A lost committed response freezes the resource and charges once."""
    state = {"credits": 2, "operations": {}, "requests": [], "drop_first": True}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state["requests"].append((self.path, dict(self.headers)))
            path = urlsplit(self.path).path
            if path == "/blockchain/get_chain_length":
                self.send_json(200, {"chain_length": 8})
                return
            if self.headers.get("Authorization") != "Bearer ytk_local_test":
                self.send_json(401, {"error": {"code": "unauthorized"}})
                return
            operation = self.headers.get("Idempotency-Key")
            assert str(UUID(operation)) == operation
            if "block_number=404" in self.path:
                self.send_json(404, {"error": {"code": "unavailable"}})
                return
            if operation not in state["operations"]:
                if not state["credits"]:
                    self.send_json(
                        402,
                        {
                            "error": {
                                "code": "insufficient_credits",
                                "required_credits": 1,
                                "available_credits": 0,
                            }
                        },
                    )
                    return
                state["credits"] -= 1
                state["operations"][operation] = copy.deepcopy(BLOCK)
            if state["drop_first"]:
                state["drop_first"] = False
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            self.send_json(
                200,
                {"block": state["operations"][operation]},
                {
                    "X-Yototec-Credits-Charged": "1",
                    "X-Yototec-Credits-Remaining": str(state["credits"]),
                    "X-Yototec-Operation-Id": operation,
                },
            )

        def send_json(self, status, payload, headers=None):
            encoded = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        with Client(
            base_url=f"http://127.0.0.1:{server.server_port}",
            api_key="ytk_local_test",
            timeout=2,
            max_retries=1,
            backoff_factor=0,
        ) as client:
            assert client.get_chain_length("mainnet") == 8
            assert state["credits"] == 2
            assert client.get_last_block("mainnet") == BLOCK
            operation = client.last_operation_id
            assert client.credits_remaining == 1
            assert len(state["operations"]) == 1
            assert client.get_last_block("mainnet", idempotency_key=operation) == BLOCK
            assert state["credits"] == 1
            assert client.get_block_by_number("mainnet", 7) == BLOCK
            assert client.credits_remaining == 0
            with pytest.raises(InsufficientCreditsError):
                client.get_block_by_number("mainnet", 7)
            with pytest.raises(APIError) as caught:
                client.get_block_by_number("mainnet", 404)
            assert caught.value.status_code == 404
            assert state["credits"] == 0
            assert len(state["operations"]) == 2
        assert len(state["requests"]) == 7
        assert all("api_key" not in path for path, _ in state["requests"])
        first, retry = state["requests"][1:3]
        assert first[1]["Idempotency-Key"] == retry[1]["Idempotency-Key"] == operation
        assert "Authorization" not in state["requests"][0][1]
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
