"""
A Python Client to interact with the SentiChain API.
"""

from typing import List, Dict, Optional, Any
import requests  # type: ignore


BASE_URL = "https://api.sentichain.com"


class Client:
    """
    A Python client that wraps interactions with the SentiChain API.
    """

    def __init__(self, base_url: str = BASE_URL, api_key: str = ""):
        """
        Initialize the client with a base URL and an optional API key.
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def get_user_info(self, user_id: str, api_key: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve user information including points remaining.
        """
        resp = requests.get(
            f"{self.base_url}/api/get_user_info?user_id={user_id}&api_key={api_key}",
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("user")
        return None

    def get_chain_length(self, network: str) -> Optional[int]:
        """
        Retrieve the current length (block count) of a specified network.
        """
        resp = requests.get(
            f"{self.base_url}/blockchain/get_chain_length?network={network}",
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("chain_length")
        return None

    def get_last_block_time(self, network: str) -> Optional[float]:
        """
        Retrieve the UTC timestamp of the last block for a specified network.
        """
        resp = requests.get(
            f"{self.base_url}/blockchain/get_last_block_time?network={network}",
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("last_block_time")
        return None

    def get_total_number_of_transactions(self, network: str) -> Optional[int]:
        """
        Retrieve the total count of confirmed (on-chain) transactions for a
        specified network.
        """
        resp = requests.get(
            f"{self.base_url}/blockchain/get_total_number_of_transactions?network={network}",
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("total_tx_count")
        return None

    def get_last_block(self, network: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve the latest block.
        If a valid query-param api_key is provided, full transactions are included.
        Otherwise, they are hidden.
        """
        resp = requests.get(
            f"{self.base_url}/blockchain/get_last_block?network={network}&api_key={self.api_key}",
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("block")
        return None

    def get_block_by_number(
        self, network: str, block_number: int
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific block by its number.
        If a valid query-param api_key is provided, full transactions are included.
        Otherwise, they are hidden.
        """
        resp = requests.get(
            f"{self.base_url}/blockchain/get_block_by_number?network={network}&block_number={block_number}&api_key={self.api_key}",
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("block")
        return None

    def get_block_number_from_timestamp(
        self, network: str, timestamp: str
    ) -> Optional[int]:
        """
        Retrieve the last availble block number less or equal to a UTC timestamp
        for a specified network.
        """
        resp = requests.get(
            f"{self.base_url}/blockchain/get_block_number_from_timestamp?network={network}&timestamp={timestamp}",
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("block_number")
        return None

    def get_timestamp_from_block_number(
        self, network: str, block_number: int
    ) -> Optional[str]:
        """
        Retrieve the UTC timestamp for a block number for a specified network.
        """
        resp = requests.get(
            f"{self.base_url}/blockchain/get_timestamp_from_block_number?network={network}&block_number={block_number}",
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("timestamp")
        return None

    def get_max_block_number(self) -> Optional[int]:
        """
        Returns the maximum block number of the Miannet blocks processed in the
        Event Map, or null if no blocks exist.
        """
        resp = requests.get(
            f"{self.base_url}/mapper/get_max_block_number",
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("max_block_number")
        return None

    def get_points_by_block_no_embedding(
        self, block_number: int
    ) -> Optional[List[List[Any]]]:
        """
        Return snapshots of Event Map for a blocks at a specified block_number.
        If a valid query-param api_key is provided, full content is included.
        Otherwise, it is hidden.
        """
        resp = requests.get(
            f"{self.base_url}/mapper/get_points_by_block_no_embedding?block_number={block_number}&api_key={self.api_key}",
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("points")
        return None

    def get_points_by_block_range_no_embedding(
        self, start_block: int, end_block: int
    ) -> Optional[List[List[Any]]]:
        """
        Return snapshots of Event Map for blocks in [start_block, end_block].
        If a valid query-param api_key is provided, full contents are included.
        Otherwise, they are hidden.
        """
        resp = requests.get(
            f"{self.base_url}/mapper/get_points_by_block_range_no_embedding?start_block={start_block}&end_block={end_block}&api_key={self.api_key}",
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("points")
        return None

    def get_reasoning_match_chunk_end(
        self, ticker: str, summary_type: str, user_chunk_end: int
    ) -> Optional[str]:
        """
        Return the reasoning for the last available chunk whose chunk_end is
        less and equal to user_chunk_end, for the given ticker and summary_type.
        If a valid query-param api_key is provided, reasoning is included.
        Otherwise, it is hidden.
        Please note, api_key is not required for summary_type ending with _public.
        """
        resp = requests.get(
            f"{self.base_url}/agent/get_reasoning_match_chunk_end?ticker={ticker}&summary_type={summary_type}&user_chunk_end={user_chunk_end}&api_key={self.api_key}",
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("reasoning")
        return None
