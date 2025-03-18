"""
Tests Client.
"""

import unittest
from sentichain.client import Client


class TestClient(unittest.TestCase):
    """
    Tests Client
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Create a single Client instance for all tests.
        """
        # Replace "YOUR_API_KEY" with a valid API key for testnet or use environment variables
        cls.api_key = "YOUR_API_KEY"  # type: ignore
        cls.client_user = Client(api_key=cls.api_key)  # type: ignore

        # Example user_id for testing (replace with a real user or mock)
        cls.test_user_id = "12345"  # type: ignore

        # Example block number(s) for testing mapper endpoints (replace with real existing blocks)
        cls.test_block_number = 1  # type: ignore
        cls.test_block_range_start = 1  # type: ignore
        cls.test_block_range_end = 3  # type: ignore

    def test_01_get_chain_length(self) -> None:
        """
        Check the chain length for 'testnet'.
        """
        chain_len = self.client_user.get_chain_length(network="testnet")  # type: ignore
        self.assertIsNotNone(chain_len, "Should retrieve chain length without error.")
        self.assertGreaterEqual(chain_len, 0, "Chain length should be >= 0.")

    def test_02_get_last_block_time(self) -> None:
        """
        Retrieve the timestamp of the last block on 'testnet'.
        """
        last_time = self.client_user.get_last_block_time(network="testnet")  # type: ignore
        self.assertIsNotNone(
            last_time, "Should retrieve a timestamp for the latest block."
        )
        self.assertGreater(last_time, 0, "Timestamp should be > 0 if a block exists.")

    def test_03_get_total_number_of_transactions(self) -> None:
        """
        Check the total number of on-chain transactions on 'testnet'.
        """
        tx_count = self.client_user.get_total_number_of_transactions(network="testnet")  # type: ignore
        self.assertIsNotNone(
            tx_count, "Should retrieve a total on-chain transaction count."
        )
        self.assertIsInstance(tx_count, int, "Transaction count should be an integer.")

    def test_04_get_last_block(self) -> None:
        """
        Retrieve the newest block from 'testnet' via the client.
        """
        block_data = self.client_user.get_last_block(network="testnet")  # type: ignore
        self.assertIsNotNone(block_data, "Should retrieve a block dictionary.")
        self.assertIn(
            "block_number", block_data, "Block data should contain 'block_number'."
        )

    def test_05_get_block_by_number(self) -> None:
        """
        Retrieve a specific block by number from 'testnet'.
        """
        # Replace 1 (or self.test_block_number) with a block known to exist
        block_data = self.client_user.get_block_by_number(  # type: ignore
            network="testnet", block_number=self.test_block_number  # type: ignore
        )
        # It's possible block #1 doesn't exist yet on your chain, so adjust to a known block.
        self.assertIsNotNone(
            block_data, "Should retrieve a block dictionary for a valid block number."
        )
        self.assertIn(
            "block_number", block_data, "Block data should contain 'block_number'."
        )

    def test_06_get_max_block_number(self) -> None:
        """
        Retrieve the maximum block number of Miannet blocks processed in the Event Map.
        """
        max_block_num = self.client_user.get_max_block_number()  # type: ignore
        # The result may be None if no Miannet blocks have been processed yet.
        # For testing purposes, just ensure no exception was raised.
        self.assertIsNotNone(
            max_block_num, "Should retrieve a max block number or 0 if no blocks exist."
        )

    def test_07_get_points_by_block_no_embedding(self) -> None:
        """
        Retrieve point snapshots for a single block from the Event Map.
        """
        # Adjust self.test_block_number to a block known to exist in the mapper.
        points = self.client_user.get_points_by_block_no_embedding(  # type: ignore
            block_number=self.test_block_number  # type: ignore
        )
        # If there's no data for that block, `points` could be None or an empty list.
        self.assertIsNotNone(
            points,
            "Expected a valid points response (could be empty, but should not error).",
        )

    def test_08_get_points_by_block_range_no_embedding(self) -> None:
        """
        Retrieve point snapshots for a range of blocks from the Event Map.
        """
        points = self.client_user.get_points_by_block_range_no_embedding(  # type: ignore
            start_block=self.test_block_range_start, end_block=self.test_block_range_end  # type: ignore
        )
        # If there's no data for that block range, `points` could be None or an empty list.
        self.assertIsNotNone(
            points,
            "Expected a valid points response for a block range (could be empty).",
        )

    def test_09_get_reasoning_match_chunk_end(self) -> None:
        """
        Retrieve reasoning for the last available chunk whose chunk_end is
        less and equal to user_chunk_end, for the given ticker and summary_type.
        """
        reasoning = self.client_user.get_reasoning_match_chunk_end(  # type: ignore
            ticker="DOGE", summary_type="observation_public", user_chunk_end=200  # type: ignore
        )
        # If there's no data for that chunk end, `reasoning` could be None or an empty str.
        self.assertIsNotNone(
            reasoning,
            "Expected a valid reasoning response (could be empty).",
        )


if __name__ == "__main__":
    unittest.main()
