"""Explicitly opted-in metadata checks; never purchase or expose source data."""

import os
from datetime import datetime

import pytest

from sentichain import Client

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("SENTICHAIN_RUN_LIVE") != "1",
        reason="Set SENTICHAIN_RUN_LIVE to enable free public metadata checks.",
    ),
]


def test_free_metadata():
    with Client(
        base_url=os.environ.get("SENTICHAIN_BASE_URL", "https://api.sentichain.com"),
        timeout=15,
        max_retries=0,
    ) as client:
        length = client.get_chain_length("mainnet")
        assert isinstance(length, int) and length > 0
        timestamp = client.get_timestamp_from_block_number("mainnet", length - 1)
        assert datetime.fromisoformat(timestamp.replace("Z", "+00:00")).tzinfo is not None
        assert client.get_block_number_from_timestamp("mainnet", timestamp) == length - 1
