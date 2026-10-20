"""Deterministic tests for HTTP requests, responses and credentials."""

import json
import traceback
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from sentichain.client import ANALYTICS_BASE_URL, BASE_URL, Client
from sentichain.exceptions import (
    APIError,
    AuthenticationError,
    RateLimitError,
    ResponseError,
    SentiChainError,
    TransportError,
)

USER = {"user_id": "alice", "name": "Alice", "email": "alice@example.org", "points": 20}
BLOCK = {
    "block_number": 7,
    "block_timestamp": 1792455038.5,
    "previous_hash": "previous",
    "hash": "hash",
    "validator": "validator",
    "consensus_root": "root",
    "transactions": {"transaction": {"post_matrix": [[0.1], [0.2]]}},
}
CASES = [
    ("get_user_info", ("alice",), "user", USER),
    ("get_chain_length", ("mainnet",), "chain_length", 8),
    ("get_last_block_time", ("testnet",), "last_block_time", 1792455038.5),
    ("get_total_number_of_transactions", ("mainnet",), "total_tx_count", 20),
    ("get_last_block", ("mainnet",), "block", BLOCK),
    ("get_block_by_number", ("testnet", 0), "block", BLOCK),
    (
        "get_block_number_from_timestamp",
        ("mainnet", "2026-10-20T00:10:39+00:00"),
        "block_number",
        7,
    ),
    ("get_timestamp_from_block_number", ("mainnet", 0), "timestamp", "2026-10-20T00:10:39Z"),
    ("get_max_block_number", (), "max_block_number", 7),
    ("get_points_by_block_no_embedding", (0,), "points", [[0, "event", "content"]]),
    ("get_points_by_block_range_no_embedding", (0, 1), "points", [{"block_number": 0}]),
    (
        "get_reasoning_match_chunk_end",
        ("BTC", "observation_public", 0),
        "reasoning",
        "Market analysis",
    ),
]


def response(payload=None, *, status=200, headers=None, raw=None):
    result = requests.Response()
    result.status_code = status
    result.headers.update(headers or {})
    result._content = json.dumps(payload).encode() if raw is None else raw
    result._content_consumed = True
    result.close = Mock()
    return result


@pytest.fixture
def session(monkeypatch):
    result = Mock(spec=requests.Session)
    monkeypatch.setattr("sentichain.client.requests.Session", lambda: result)
    return result


@pytest.fixture
def client(session):
    with Client(api_key="private-key", max_retries=0) as result:
        yield result


@pytest.mark.parametrize("method,args,field,value", CASES, ids=[case[0] for case in CASES])
def test_all_methods_preserve_results(client, session, method, args, field, value):
    result = response({field: value})
    session.get.return_value = result
    assert getattr(client, method)(*args) == value
    result.close.assert_called_once()
    assert session.get.call_args.kwargs["allow_redirects"] is False
    assert session.get.call_args.kwargs["timeout"] == 30


@pytest.mark.parametrize("method,args,field,value", CASES, ids=[case[0] for case in CASES])
def test_all_methods_preserve_null(client, session, method, args, field, value):
    session.get.return_value = response({field: None})
    assert getattr(client, method)(*args) is None


@pytest.mark.parametrize("method,args,field,value", CASES, ids=[case[0] for case in CASES])
def test_wrong_success_types_raise(client, session, method, args, field, value):
    invalid = {"reasoning": [], "timestamp": 42, "user": {}, "block": {}, "points": [42]}.get(
        field, True
    )
    session.get.return_value = response({field: invalid})
    with pytest.raises(ResponseError):
        getattr(client, method)(*args)


def test_complete_matrices_requested_by_default(client, session):
    for method, args in [("get_last_block", ("mainnet",)), ("get_block_by_number", ("mainnet", 0))]:
        session.get.return_value = response({"block": BLOCK})
        assert getattr(client, method)(*args)["transactions"] == BLOCK["transactions"]
        assert session.get.call_args.kwargs["params"]["full_embedding"] == "true"
        getattr(client, method)(*args, full_embedding=False)
        assert "full_embedding" not in session.get.call_args.kwargs["params"]


def test_user_key_reuse_and_override(client, session):
    session.get.return_value = response({"user": USER})
    for override, expected in [
        ({}, "private-key"),
        ({"api_key": "another-key"}, "another-key"),
        ({"api_key": ""}, ""),
    ]:
        client.get_user_info("alice", **override)
        assert session.get.call_args.kwargs["params"]["api_key"] == expected


def test_reserved_and_unicode_values_encoded(monkeypatch):
    prepared = []

    def send(session, request, **kwargs):
        prepared.append((request, kwargs))
        field = "block_number" if "timestamp" in request.url else "user"
        return response({field: 7 if field == "block_number" else USER})

    monkeypatch.setattr(requests.Session, "send", send)
    key = "secret&+?雪"
    with Client(api_key=key) as client:
        client.get_user_info("a&b +雪")
        client.get_block_number_from_timestamp("mainnet", "2026-10-20T05:40:39+05:30")
    assert parse_qs(urlsplit(prepared[0][0].url).query) == {
        "user_id": ["a&b +雪"],
        "api_key": [key],
    }
    assert parse_qs(urlsplit(prepared[1][0].url).query)["timestamp"] == [
        "2026-10-20T05:40:39+05:30"
    ]
    assert "%2B05%3A30" in prepared[1][0].url
    assert all(kwargs["allow_redirects"] is False for _, kwargs in prepared)


def test_analysis_destination_and_credential_isolation(client, session):
    session.get.return_value = response({"reasoning": "hidden"})
    assert client.get_reasoning_match_chunk_end("BTC&ETH", "observation_public", 0) == "hidden"
    assert (
        session.get.call_args.args[0] == ANALYTICS_BASE_URL + "/agent/get_reasoning_match_chunk_end"
    )
    assert "api_key" not in session.get.call_args.kwargs["params"]
    assert "headers" not in session.get.call_args.kwargs


def test_configurable_destinations_and_timeout(session):
    session.get.return_value = response({"reasoning": None})
    with Client(
        "http://localhost:8000/service/",
        timeout=(1, 3),
        analytics_base_url="https://analysis.example/base/",
    ) as client:
        client.get_reasoning_match_chunk_end("BTC", "observation_public", 1)
        assert (
            session.get.call_args.args[0]
            == "https://analysis.example/base/agent/get_reasoning_match_chunk_end"
        )
        assert session.get.call_args.kwargs["timeout"] == (1, 3)
        assert client.base_url == "http://localhost:8000/service"


@pytest.mark.parametrize(
    "status,exception",
    [
        (400, APIError),
        (401, AuthenticationError),
        (403, AuthenticationError),
        (404, APIError),
        (429, RateLimitError),
        (500, APIError),
        (502, APIError),
        (301, APIError),
        (302, APIError),
        (307, APIError),
        (308, APIError),
    ],
)
def test_http_errors_explicit_and_private(client, session, status, exception):
    result = response(
        {"error": "private-key https://unsafe.example/?api_key=private-key"},
        status=status,
        headers={"Location": "https://unsafe.example/?api_key=private-key"},
    )
    session.get.return_value = result
    with pytest.raises(exception) as caught:
        client.get_max_block_number()
    assert caught.value.status_code == status
    assert "private-key" not in str(caught.value)
    assert "unsafe.example" not in str(caught.value)
    result.close.assert_called_once()
    assert session.get.call_count == 1


@pytest.mark.parametrize(
    "error", [requests.Timeout, requests.ConnectionError, requests.RequestException]
)
def test_network_errors_sanitized(client, session, error):
    session.get.side_effect = error("https://api.example/?api_key=private-key")
    with pytest.raises(TransportError) as caught:
        client.get_user_info("alice")
    rendered = "".join(traceback.format_exception(caught.type, caught.value, caught.tb))
    assert "private-key" not in str(caught.value)
    assert "api.example" not in rendered


@pytest.mark.parametrize(
    "payload",
    [
        [],
        None,
        {"other": 2},
        {"max_block_number": -1},
        {"max_block_number": "7"},
        {"max_block_number": True},
    ],
)
def test_malformed_envelopes(client, session, payload):
    result = response(payload)
    session.get.return_value = result
    with pytest.raises(ResponseError):
        client.get_max_block_number()
    result.close.assert_called_once()


def test_invalid_json(client, session):
    result = response(raw=b"not json private-key")
    session.get.return_value = result
    with pytest.raises(ResponseError, match="not valid JSON") as caught:
        client.get_max_block_number()
    assert "private-key" not in str(caught.value)
    result.close.assert_called_once()


def test_retries_bounded_and_responses_closed(session, monkeypatch):
    sleeps = Mock()
    monkeypatch.setattr("sentichain.client.time.sleep", sleeps)
    results = [response({}, status=503) for _ in range(4)]
    session.get.side_effect = results
    with Client(max_retries=3, backoff_factor=2, max_backoff=3) as client:
        with pytest.raises(APIError) as caught:
            client.get_max_block_number()
    assert caught.value.status_code == 503
    assert session.get.call_count == 4
    assert [call.args[0] for call in sleeps.call_args_list] == [2, 3, 3]
    for result in results:
        result.close.assert_called_once()


def test_network_retry_can_recover(session, monkeypatch):
    monkeypatch.setattr("sentichain.client.time.sleep", Mock())
    session.get.side_effect = [requests.Timeout("private-key"), response({"max_block_number": 0})]
    with Client(max_retries=1) as client:
        assert client.get_max_block_number() == 0
    assert session.get.call_count == 2


def test_retry_after_recoverable_rate_limit(session, monkeypatch):
    sleeps = Mock()
    monkeypatch.setattr("sentichain.client.time.sleep", sleeps)
    limited = response({}, status=429, headers={"Retry-After": "2"})
    session.get.side_effect = [limited, response({"max_block_number": 0})]
    with Client(max_retries=1) as client:
        assert client.get_max_block_number() == 0
    sleeps.assert_called_once_with(2)
    limited.close.assert_called_once()


@pytest.mark.parametrize(
    "header,expected", [("900", 900), ("2", 2), ("bad date", None), ("nan", None), ("-1", None)]
)
def test_rate_limit_delay_exposed(client, session, header, expected):
    session.get.return_value = response({}, status=429, headers={"Retry-After": header})
    with pytest.raises(RateLimitError) as caught:
        client.get_max_block_number()
    assert caught.value.retry_after == expected


def test_long_retry_after_does_not_retry_early(session, monkeypatch):
    sleeps = Mock()
    monkeypatch.setattr("sentichain.client.time.sleep", sleeps)
    session.get.return_value = response({}, status=429, headers={"Retry-After": "900"})
    with Client(max_retries=5, max_backoff=3) as client:
        with pytest.raises(RateLimitError) as caught:
            client.get_max_block_number()
    assert caught.value.retry_after == 900
    assert session.get.call_count == 1
    sleeps.assert_not_called()


def test_retry_after_http_date(client, session):
    deadline = datetime.now(timezone.utc) + timedelta(seconds=60)
    session.get.return_value = response(
        {}, status=429, headers={"Retry-After": format_datetime(deadline, usegmt=True)}
    )
    with pytest.raises(RateLimitError) as caught:
        client.get_max_block_number()
    assert 58 <= caught.value.retry_after <= 61


def test_context_closes_and_disallows_reuse(session):
    with pytest.raises(RuntimeError):
        with Client() as client:
            raise RuntimeError("caller failure")
    session.close.assert_called_once()
    client.close()
    session.close.assert_called_once()
    with pytest.raises(SentiChainError, match="closed"):
        client.get_max_block_number()
    with pytest.raises(SentiChainError, match="closed"):
        client.__enter__()
    session.get.assert_not_called()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_url": "ftp://example.org"},
        {"base_url": "https://user:password@example.org"},
        {"base_url": "https://example.org/?secret=x"},
        {"base_url": "https://example.org/#fragment"},
        {"base_url": "https://example.org:bad"},
        {"base_url": "https://example.org:0"},
        {"base_url": "https://"},
        {"base_url": "https://example.org\\bad"},
        {"analytics_base_url": "https://example.org?"},
        {"base_url": " https://example.org"},
        {"api_key": None},
        {"timeout": 0},
        {"timeout": -1},
        {"timeout": float("inf")},
        {"timeout": float("nan")},
        {"timeout": True},
        {"timeout": (1, 0)},
        {"timeout": (1, 2, 3)},
        {"timeout": None},
        {"max_retries": True},
        {"max_retries": -1},
        {"max_retries": 6},
        {"max_retries": 0.5},
        {"backoff_factor": -1},
        {"max_backoff": float("inf")},
    ],
)
def test_constructor_validation_before_session(session, kwargs):
    with pytest.raises(ValueError):
        Client(**kwargs)
    session.get.assert_not_called()


@pytest.mark.parametrize(
    "method,args,kwargs",
    [
        ("get_chain_length", ("invalid",), {}),
        ("get_chain_length", (None,), {}),
        ("get_block_by_number", ("mainnet", -1), {}),
        ("get_block_by_number", ("mainnet", True), {}),
        ("get_timestamp_from_block_number", ("mainnet", 1.0), {}),
        ("get_points_by_block_no_embedding", (False,), {}),
        ("get_points_by_block_range_no_embedding", (2, 1), {}),
        ("get_points_by_block_range_no_embedding", (0, True), {}),
        ("get_last_block", ("mainnet",), {"full_embedding": "false"}),
        ("get_block_by_number", ("mainnet", 0), {"full_embedding": 1}),
        ("get_block_number_from_timestamp", ("mainnet", "2026-10-20T00:10:39"), {}),
        ("get_block_number_from_timestamp", ("mainnet", "not a timestamp"), {}),
        ("get_block_number_from_timestamp", ("mainnet", 1792455039), {}),
        ("get_user_info", (" ",), {}),
        ("get_user_info", ("alice",), {"api_key": 12}),
        ("get_reasoning_match_chunk_end", ("", "observation_public", 0), {}),
        ("get_reasoning_match_chunk_end", ("BTC", " ", 0), {}),
        ("get_reasoning_match_chunk_end", ("BTC", "observation_public", True), {}),
    ],
)
def test_method_input_validation(client, session, method, args, kwargs):
    with pytest.raises(ValueError):
        getattr(client, method)(*args, **kwargs)
    session.get.assert_not_called()


def test_zero_and_empty_success_results(client, session):
    session.get.return_value = response({"chain_length": 0})
    assert client.get_chain_length("mainnet") == 0
    session.get.return_value = response({"points": []})
    assert client.get_points_by_block_no_embedding(0) == []
    session.get.return_value = response({"reasoning": ""})
    assert client.get_reasoning_match_chunk_end("BTC", "observation_public", 0) == ""


def test_default_service_url(client, session):
    session.get.return_value = response({"max_block_number": 0})
    client.get_max_block_number()
    assert session.get.call_args.args[0] == BASE_URL + "/mapper/get_max_block_number"
