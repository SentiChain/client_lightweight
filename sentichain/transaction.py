"""
Transaction module for SentiChain blockchain.

This module defines the Transaction class and related utilities for handling
sentiment analysis transactions in the SentiChain blockchain. Each transaction
represents a sentiment analysis result for a social media post, including:
- The original post's metadata (timestamp, link)
- The sentiment analysis matrix and its signature
- Cryptographic verification of the transaction
"""

from typing import Dict, List, Optional, Any
import time
import logging
import json
import hashlib

from cryptography.hazmat.primitives import hashes  # type: ignore
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # type: ignore
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_public_key,
)  # type: ignore
from cryptography.exceptions import InvalidSignature  # type: ignore


logger = logging.getLogger(__name__)


class Transaction:
    """
    Represents a sentiment analysis transaction in the SentiChain blockchain.

    Each transaction contains:
    - sender:           The identifier (address) of the entity submitting the sentiment analysis
    - public_key:       RSA public key (PEM-encoded) used to verify the transaction signature
    - post_timestamp:   Unix timestamp of when the original post was created
    - post_link:        URL or link to the original social media post
    - post_matrix:      The sentiment analysis matrix generated for the post
    - matrix_signature: Digital signature of the matrix from SentiChain Vectorizer
    - source:           Source platform of the post (optional, for internal use only)
    - nonce:            Unique number to prevent transaction replay attacks
    - transaction_timestamp: Unix time when this transaction was created
    """

    def __init__(
        self,
        sender: str,
        public_key: rsa.RSAPublicKey,
        post_timestamp: float,
        post_link: str,
        post_matrix: str,
        matrix_signature: str,
        source: str,
        nonce: int = 1,
    ) -> None:
        """
        Initializes a new Transaction instance.
        """
        self.sender: str = sender
        self.public_key: rsa.RSAPublicKey = public_key
        self.post_timestamp: float = post_timestamp
        self.post_link: str = post_link
        self.post_matrix: List[List[float]] = post_matrix
        self.matrix_signature: str = matrix_signature
        self.source: str = source

        # Internally assigned fields
        self.transaction_timestamp: float = time.time()
        self.nonce: int = nonce

    def to_dict(self) -> Dict[str, Any]:
        """
        Converts the transaction fields into a dictionary for serialization.
        This method prepares the transaction data for signing and storage,
        excluding the signature which is added later in serialize().

        Returns:
            Dict[str, Any]: Dictionary containing all transaction fields in a format
            suitable for JSON serialization.
        """
        return {
            "sender": self.sender,
            "public_key": self.public_key.public_bytes(
                Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
            ).decode(),
            "post_timestamp": self.post_timestamp,
            "post_link": self.post_link,
            "post_matrix": self.post_matrix,
            "matrix_signature": self.matrix_signature,
            "source": self.source,
            "nonce": self.nonce,
            "transaction_timestamp": self.transaction_timestamp,
        }

    def sign_transaction(self, private_key: rsa.RSAPrivateKey) -> bytes:
        """
        Signs the transaction data using RSA-PSS with SHA-256.
        The transaction data is first converted to a sorted JSON string to ensure
        deterministic signing regardless of field order.

        Args:
            private_key (rsa.RSAPrivateKey): The private key corresponding to the
            transaction's public key.

        Returns:
            bytes: The digital signature of the transaction data.
        """
        transaction_details = json.dumps(self.to_dict(), sort_keys=True).encode("utf-8")
        signature = private_key.sign(
            transaction_details,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return signature

    def serialize(self, signature: bytes) -> str:
        """
        Serializes the complete transaction including its signature into a JSON string.
        The signature is included as a hex-encoded string for easy storage and transmission.

        Args:
            signature (bytes): The digital signature from sign_transaction().

        Returns:
            str: JSON-formatted string containing all transaction fields and signature.
        """
        tx_data = self.to_dict()
        tx_data["signature"] = signature.hex()
        return json.dumps(tx_data, sort_keys=True)


def generate_transaction_hash(transaction_json: str) -> str:
    """
    Generates a SHA-256 hash of the transaction JSON string.
    The transaction data is sorted by keys before hashing to ensure
    deterministic hashing regardless of field order.

    Args:
        transaction_json (str): The JSON string representation of the transaction.

    Returns:
        str: Hex-encoded SHA-256 hash of the sorted transaction data.

    Raises:
        ValueError: If the transaction_json is invalid JSON.
    """
    try:
        tx = json.loads(transaction_json)
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON for transaction.")

    sorted_tx = json.dumps(tx, sort_keys=True).encode("utf-8")
    return hashlib.sha256(sorted_tx).hexdigest()


def verify_signature(transaction_json: str) -> bool:
    """
    Verifies the RSA-PSS signature of a transaction using SHA-256.
    The transaction must contain both the public key (PEM format) and
    the signature (hex-encoded) fields.

    Args:
        transaction_json (str): The JSON string containing the transaction data,
        public key, and signature.

    Returns:
        bool: True if the signature is valid and matches the transaction data;
              False otherwise.
    """
    try:
        transaction = json.loads(transaction_json)
    except json.JSONDecodeError:
        logger.error("Invalid transaction JSON.")
        return False

    sig_hex = transaction.pop("signature", None)
    pub_key_pem_str = transaction.get("public_key")

    if not sig_hex or not pub_key_pem_str:
        logger.error("Transaction missing 'signature' or 'public_key'.")
        return False

    try:
        signature = bytes.fromhex(sig_hex)
    except ValueError:
        logger.error("Signature field is not valid hex.")
        return False

    pub_key_pem = pub_key_pem_str.encode()
    try:
        public_key = load_pem_public_key(pub_key_pem)
    except ValueError:
        logger.error("Invalid public key format.")
        return False

    # Re-create the transaction data (without signature) in sorted order
    tx_data = json.dumps(transaction, sort_keys=True).encode("utf-8")

    # Verify
    try:
        public_key.verify(  # type: ignore
            signature,  # type: ignore
            tx_data,  # type: ignore
            padding.PSS(  # type: ignore
                mgf=padding.MGF1(hashes.SHA256()),  # type: ignore
                salt_length=padding.PSS.MAX_LENGTH,  # type: ignore
            ),  # type: ignore
            hashes.SHA256(),  # type: ignore
        )
        return True
    except InvalidSignature:
        logger.warning("Signature verification failed.")
        return False
