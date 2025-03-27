"""
The Transaction class for SentiChain, including cryptographic utils for
RSA-based signing and signature verification.
"""

from typing import Dict, Any
import time
from datetime import datetime, timezone
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


def _to_iso_utc(ts: float) -> str:
    """
    Convert a float timestamp (seconds since epoch) to an ISO-8601 UTC string
    like '2025-01-01T00:00:00Z'.
    """
    ts_rounded = round(ts)
    dt = datetime.utcfromtimestamp(ts_rounded).replace(tzinfo=timezone.utc)
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


class Transaction:
    """
    Represents a single transaction for SentiChain.

    Fields:
      - sender:           The identifier (address) of whoever is submitting the summary.
      - public_key:       RSA public key (PEM-encoded) used to verify the transaction signature.
      - post_timestamp:   The original post's creation time (Unix timestamp).
      - post_link:        A URL or link to the post.
      - prompt_hash:      The SHA-256 hash of the summary prompt (which must include the raw post text).
      - post_summary:     The plaintext AI-generated summary of the post.
      - response_hash:    The SHA-256 hash of post_summary.
      - transaction_timestamp: Unix time when this transaction object was created (auto-generated).
      - nonce:            A unique number to prevent replay attacks.
    """

    def __init__(
        self,
        sender: str,
        public_key: rsa.RSAPublicKey,
        post_timestamp: float,
        post_link: str,
        prompt_hash: str,
        post_summary: str,
        response_hash: str,
        nonce: int = 1,
    ) -> None:
        """
        Initializes a new Transaction instance.
        """
        self.sender: str = sender
        self.public_key: rsa.RSAPublicKey = public_key
        self.post_timestamp: float = post_timestamp
        self.post_link: str = post_link
        self.prompt_hash: str = prompt_hash
        self.post_summary: str = post_summary
        self.response_hash: str = response_hash

        # Internally assigned fields
        self.transaction_timestamp: float = time.time()
        self.nonce: int = nonce

    @staticmethod
    def create_ai_summary_transaction(
        sender: str,
        public_key: rsa.RSAPublicKey,
        post_timestamp: float,
        post_link: str,
        prompt_hash: str,
        post_summary: str,
        nonce: int = 1,
    ) -> "Transaction":
        """
        Helper to create a new Transaction for SentiChain.
        Automatically computes response_hash = SHA256(post_summary).

        Args:
            sender:         Sender's identifier/address.
            public_key:     Sender's RSA public key (for verification).
            post_timestamp: Original post's creation time (Unix).
            post_link:      Link to the post.
            prompt_hash:    SHA-256 hash of the summary prompt (which must include raw post text).
            post_summary:   Plaintext AI-generated summary of the post.
            nonce:          A unique number to prevent replay attacks.

        Returns:
            Transaction: A properly initialized Transaction object.
        """
        response_hash = hashlib.sha256(post_summary.encode("utf-8")).hexdigest()

        return Transaction(
            sender=sender,
            public_key=public_key,
            post_timestamp=post_timestamp,
            post_link=post_link,
            prompt_hash=prompt_hash,
            post_summary=post_summary,
            response_hash=response_hash,
            nonce=nonce,
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Converts the transaction fields into a dict suitable for serialization.
        (Does not include the signature, which will be added in `serialize()`.)

        Returns:
            Dict[str, Any]: A dictionary of all transaction fields.
        """
        return {
            "sender": self.sender,
            "public_key": self.public_key.public_bytes(
                Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
            ).decode(),
            "post_timestamp": self.post_timestamp,
            "post_link": self.post_link,
            "prompt_hash": self.prompt_hash,
            "post_summary": self.post_summary,
            "response_hash": self.response_hash,
            "transaction_timestamp": _to_iso_utc(self.transaction_timestamp),
            "nonce": self.nonce,
        }

    def sign_transaction(self, private_key: rsa.RSAPrivateKey) -> bytes:
        """
        Signs the transaction JSON (sorted by keys) using the sender's RSA private key.

        Args:
            private_key (rsa.RSAPrivateKey): The private key corresponding to self.public_key.

        Returns:
            bytes: The digital signature of the transaction.
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
        Serializes the transaction into a JSON string, including the signature as hex.

        Args:
            signature (bytes): The digital signature from sign_transaction().

        Returns:
            str: JSON-formatted string with signature included.
        """
        tx_data = self.to_dict()
        tx_data["signature"] = signature.hex()
        return json.dumps(tx_data, sort_keys=True)


def generate_transaction_hash(transaction_json: str) -> str:
    """
    Generates a SHA-256 hash for the given transaction JSON string.
    The transaction is parsed, sorted by keys, and then hashed.

    Args:
        transaction_json (str): The JSON string of the transaction.

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
    Verifies the RSA signature for a transaction JSON. The transaction must
    have "public_key" (PEM) and "signature" (hex) fields.

    Args:
        transaction_json (str): The JSON string.

    Returns:
        bool: True if the signature is valid; False otherwise.
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

    # Convert to bytes
    try:
        signature = bytes.fromhex(sig_hex)
    except ValueError:
        logger.error("Signature field is not valid hex.")
        return False

    # Load the public key
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


def verify_ai_summary_fields(transaction_json: str) -> bool:
    """
    Additional check to ensure 'post_summary' and 'response_hash' match.

    (Assumes RSA signature was already verified.)

    Args:
        transaction_json (str): The JSON string (including 'post_summary' & 'response_hash').

    Returns:
        bool: True if the fields match or if absent; False otherwise.
    """
    try:
        tx = json.loads(transaction_json)
    except json.JSONDecodeError:
        logger.error("Invalid transaction JSON in verify_ai_summary_fields.")
        return False

    post_summary = tx.get("post_summary")
    response_hash = tx.get("response_hash")
    prompt_hash = tx.get("prompt_hash")

    if not post_summary and not response_hash and not prompt_hash:
        return True

    if prompt_hash and len(prompt_hash) != 64:
        logger.warning("prompt_hash is not 64 hex characters.")
        return False

    if post_summary and response_hash:
        calc_hash = hashlib.sha256(post_summary.encode("utf-8")).hexdigest()
        if calc_hash != response_hash:
            logger.warning("response_hash mismatch with post_summary.")
            return False

    return True
