"""
Tests Transaction and utils for managing keys.
"""

import json
import unittest

from sentichain.transaction import (  # type: ignore
    Transaction,  # type: ignore
    verify_signature,  # type: ignore
    generate_transaction_hash,  # type: ignore
)
from sentichain.keys import generate_key_pair  # type: ignore


class TestTransaction(unittest.TestCase):
    """
    Tests Transaction and associated cryptographic utils.
    """

    def test_create_and_verify_transaction(self) -> None:
        """
        1) Generate a key pair
        2) Create a new transaction
        3) Sign the transaction
        4) Check signature verification
        """
        # 1) Generate RSA key pair
        private_key, public_key = generate_key_pair()

        # 2) Create transaction
        post_timestamp = 1672531200.0  # e.g., 2023-01-01 00:00:00 UTC
        post_link = "https://sentichain.com/someuser/status/12345"
        sender = "Alice"

        # Create a mock sentiment analysis matrix and signature
        post_matrix = [[0.5, 0.3, 0.2], [0.1, 0.7, 0.2]]
        matrix_signature = "mock_signature"
        source = "sentichain"

        tx_obj = Transaction(
            sender=sender,
            public_key=public_key,
            post_timestamp=post_timestamp,
            post_link=post_link,
            post_matrix=post_matrix,
            matrix_signature=matrix_signature,
            source=source,
            nonce=42,
        )

        # 3) Sign transaction
        signature = tx_obj.sign_transaction(private_key)
        serialized_tx = tx_obj.serialize(signature)

        # 4) Verify the signature
        self.assertTrue(
            verify_signature(serialized_tx), "RSA signature should be valid"
        )

    def test_tampered_data(self) -> None:
        """
        Verify that if the transaction data is tampered after signing,
        signature verification will fail.
        """
        private_key, public_key = generate_key_pair()

        # Create a mock sentiment analysis matrix and signature
        post_matrix = [[0.4, 0.4, 0.2], [0.2, 0.6, 0.2]]
        matrix_signature = "mock_signature"
        source = "sentichain"

        tx_obj = Transaction(
            sender="Bob",
            public_key=public_key,
            post_timestamp=1000.0,
            post_link="https://sentichain.com/post/999",
            post_matrix=post_matrix,
            matrix_signature=matrix_signature,
            source=source,
            nonce=1,
        )

        signature = tx_obj.sign_transaction(private_key)
        serialized = tx_obj.serialize(signature)

        # Tamper with the data in the JSON
        tx_dict = json.loads(serialized)
        tx_dict["post_link"] = "https://sentichain.com/tampered/post"
        tampered_tx_json = json.dumps(tx_dict, sort_keys=True)

        # The RSA signature check should fail because we changed the data but not the signature
        signature_ok = verify_signature(tampered_tx_json)
        self.assertFalse(
            signature_ok, "Signature should fail if we changed transaction data."
        )

    def test_tampered_signature(self) -> None:
        """
        Verify that if the signature is altered, the RSA check fails.
        """
        private_key, public_key = generate_key_pair()

        # Create a mock sentiment analysis matrix and signature
        post_matrix = [[0.3, 0.5, 0.2], [0.3, 0.5, 0.2]]
        matrix_signature = "mock_signature"
        source = "sentichain"

        tx_obj = Transaction(
            sender="Eve",
            public_key=public_key,
            post_timestamp=1000.0,
            post_link="https://sentichain.com/post/abc",
            post_matrix=post_matrix,
            matrix_signature=matrix_signature,
            source=source,
            nonce=1,
        )

        signature = tx_obj.sign_transaction(private_key)
        serialized = tx_obj.serialize(signature)

        # Convert to dict and tamper with 'signature' field
        tx_dict = json.loads(serialized)
        tx_dict["signature"] = "0000deadbeef"  # random hex
        tampered_tx_json = json.dumps(tx_dict, sort_keys=True)

        self.assertFalse(
            verify_signature(tampered_tx_json),
            "Signature verification should fail if the signature is tampered.",
        )

    def test_generate_transaction_hash(self) -> None:
        """
        Verify we can generate a SHA-256 transaction hash from the JSON.
        """
        # Minimal transaction JSON
        tx_json = json.dumps(
            {
                "sender": "Carol",
                "public_key": "FAKE-PEM-KEY",
                "post_timestamp": "2025-03-25T09:36:26Z",
                "post_link": "https://sentichain.com/some/status/999",
                "post_matrix": [[0.1, 0.2, 0.7], [0.6, 0.2, 0.2]],
                "matrix_signature": "mock_signature",
                "source": "sentichain",
                "transaction_timestamp": "2025-03-25T09:36:26Z",
                "nonce": 2,
                "signature": "ff" * 128,  # Some hex signature
            },
            sort_keys=True,
        )

        # Just ensure we can compute a SHA-256 hash from it
        tx_hash = generate_transaction_hash(tx_json)
        self.assertEqual(
            len(tx_hash), 64, "Transaction hash should be 64 hex characters."
        )
        # We can also do a quick test for hex-ness:
        int(tx_hash, 16)  # no error means it's valid hex


if __name__ == "__main__":
    unittest.main()
