"""
Tests Transaction and utils for managing keys.
"""

import json
import unittest

from sentichain.transaction import (  # type: ignore
    Transaction,  # type: ignore
    verify_signature,  # type: ignore
    verify_ai_summary_fields,  # type: ignore
    generate_transaction_hash,  # type: ignore
)
from sentichain.keys import generate_key_pair  # type: ignore


class TestTransaction(unittest.TestCase):
    """
    Tests Transaction and associated cryptographic utils.
    """

    def test_create_and_verify_ai_transaction(self) -> None:
        """
        1) Generate a key pair
        2) Create a new AI summary transaction (with required fields)
        3) Sign the transaction
        4) Check signature verification
        5) Check AI summary fields (prompt_hash, post_summary, response_hash)
        """
        # 1) Generate RSA key pair
        private_key, public_key = generate_key_pair()

        # 2) Create transaction
        post_timestamp = 1672531200.0  # e.g., 2023-01-01 00:00:00 UTC
        post_link = "https://sentichain.com/someuser/status/12345"
        prompt_hash = (
            "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"  # 64 hex
        )
        post_summary = "Post about an upcoming product launch."
        sender = "Alice"

        tx_obj = Transaction.create_ai_summary_transaction(
            sender=sender,
            public_key=public_key,
            post_timestamp=post_timestamp,
            post_link=post_link,
            prompt_hash=prompt_hash,
            post_summary=post_summary,
            nonce=42,
        )

        # 3) Sign transaction
        signature = tx_obj.sign_transaction(private_key)
        serialized_tx = tx_obj.serialize(signature)

        # 4) Verify the signature
        self.assertTrue(
            verify_signature(serialized_tx), "RSA signature should be valid"
        )

        # 5) Verify AI summary fields
        self.assertTrue(
            verify_ai_summary_fields(serialized_tx),
            "AI summary fields should be valid (response_hash matches post_summary).",
        )

    def test_tampered_post_summary(self) -> None:
        """
        Verify that if the post_summary is tampered after signing,
        signature verification might still pass (since we didn't change signature field),
        but AI summary fields check will fail (response_hash mismatch).
        """
        private_key, public_key = generate_key_pair()

        tx_obj = Transaction.create_ai_summary_transaction(
            sender="Bob",
            public_key=public_key,
            post_timestamp=1000.0,
            post_link="https://sentichain.com/post/999",
            prompt_hash="abcdef" + "0" * 58,  # 64 hex total
            post_summary="Original summary",
            nonce=1,
        )
        signature = tx_obj.sign_transaction(private_key)
        serialized = tx_obj.serialize(signature)

        # Tamper the "post_summary" field in the JSON
        tx_dict = json.loads(serialized)
        tx_dict["post_summary"] = "Tampered summary"
        tampered_tx_json = json.dumps(tx_dict, sort_keys=True)

        # The RSA signature check might still pass or fail depending on how we tamper
        signature_ok = verify_signature(tampered_tx_json)
        # We'll check that in this example, the signature will FAIL because the tampered
        # data doesn't match the originally signed data.
        self.assertFalse(
            signature_ok, "Signature should fail if we changed post_summary."
        )

        # But even if the signature somehow passed, the AI fields check would fail:
        # We'll check that as well:
        self.assertFalse(
            verify_ai_summary_fields(tampered_tx_json),
            "AI summary fields must fail (response_hash mismatch) on tampered summary.",
        )

    def test_tampered_signature(self) -> None:
        """
        Verify that if the signature is altered, the RSA check fails.
        """
        private_key, public_key = generate_key_pair()

        tx_obj = Transaction.create_ai_summary_transaction(
            sender="Eve",
            public_key=public_key,
            post_timestamp=1000.0,
            post_link="https://sentichain.com/post/abc",
            prompt_hash="a" * 64,
            post_summary="Something about a new product",
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
                "prompt_hash": "0" * 64,
                "post_summary": "Just a summary",
                "response_hash": "abcd" * 16,  # 64 hex
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
