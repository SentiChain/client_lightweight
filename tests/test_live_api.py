"""Read-only checks for public API responses and signed transaction data."""

import json
import os
from datetime import datetime

import pytest

from sentichain import Client, generate_transaction_hash, verify_signature

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("SENTICHAIN_RUN_LIVE") != "1",
        reason="Set SENTICHAIN_RUN_LIVE to enable public API checks.",
    ),
]


@pytest.fixture
def client():
    with Client(
        base_url=os.environ.get("SENTICHAIN_BASE_URL", "https://api.sentichain.com"),
        analytics_base_url=os.environ.get(
            "SENTICHAIN_ANALYTICS_BASE_URL", "https://api.sentimove.com"
        ),
        api_key=os.environ.get("SENTICHAIN_API_KEY", ""),
    ) as value:
        yield value


@pytest.mark.parametrize("network", ["mainnet", "testnet"])
def test_chain_counts_and_timestamps(client, network):
    length = client.get_chain_length(network)
    assert isinstance(length, int) and length > 0
    assert client.get_last_block_time(network) > 0
    assert client.get_total_number_of_transactions(network) >= 0
    block_number = length - 1
    block = client.get_block_by_number(network, block_number)
    assert block["block_number"] == block_number
    assert isinstance(block["transactions"], dict)
    assert client.get_last_block(network)["block_number"] >= block_number
    timestamp = client.get_timestamp_from_block_number(network, block_number)
    assert datetime.fromisoformat(timestamp.replace("Z", "+00:00")).tzinfo is not None
    assert client.get_block_number_from_timestamp(network, timestamp) == block_number
    assert (
        client.get_block_number_from_timestamp(network, timestamp.replace("Z", "+00:00"))
        == block_number
    )


def test_mapper_snapshots(client):
    block_number = client.get_max_block_number()
    assert isinstance(block_number, int) and block_number >= 0
    points = client.get_points_by_block_no_embedding(block_number)
    assert isinstance(points, list) and points
    assert all(isinstance(row, (list, dict)) for row in points)
    assert client.get_points_by_block_range_no_embedding(block_number, block_number) == points


@pytest.mark.parametrize("summary_type", ["sm_events", "sm_signal"])
def test_analytics_content(client, summary_type):
    cutoff = client.get_chain_length("mainnet") - 1
    reasoning = client.get_reasoning_match_chunk_end("BTC", summary_type, cutoff)
    assert isinstance(reasoning, str) and reasoning.strip()
    result = json.loads(reasoning)
    if summary_type == "sm_events":
        assert isinstance(result, list) and result
        for event in result:
            assert isinstance(event, dict)
            assert all(
                isinstance(event.get(field), str) and event[field].strip()
                for field in ("timestamp", "event", "sentiment", "summary")
            )
            assert datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).tzinfo
    else:
        assert isinstance(result, dict)
        assert result.get("direction") in {"UP", "DOWN", "FLAT"}
        assert isinstance(result.get("confidence"), (int, float))
        assert 0 <= result["confidence"] <= 1
        assert isinstance(result.get("rationale"), str) and result["rationale"].strip()


def test_account_information(client):
    user_id = os.environ.get("SENTICHAIN_USER_ID")
    if not user_id or not client.api_key:
        pytest.skip("An account ID and API key are required for account checks.")
    user = client.get_user_info(user_id)
    assert user["user_id"] == user_id
    assert isinstance(user["points"], int)


def test_complete_signed_transactions(client):
    if os.environ.get("SENTICHAIN_VERIFY_SIGNATURES") != "1":
        pytest.skip("Set SENTICHAIN_VERIFY_SIGNATURES for access to unredacted signed data.")
    newest = client.get_chain_length("mainnet") - 1
    for number in range(newest, max(-1, newest - 12), -1):
        block = client.get_block_by_number("mainnet", number)
        if block["transactions"]:
            break
    else:
        pytest.fail("No signed transaction was available in the requested block range.")
    compact = client.get_block_by_number("mainnet", number, full_embedding=False)
    assert set(compact["transactions"]) == set(block["transactions"])
    for tx_hash, transaction in block["transactions"].items():
        serialized = json.dumps(transaction, sort_keys=True)
        assert verify_signature(serialized)
        assert generate_transaction_hash(serialized) == tx_hash
        matrix = transaction["post_matrix"]
        assert isinstance(matrix, list) and matrix
        assert len(compact["transactions"][tx_hash]["post_matrix"]) == 1
