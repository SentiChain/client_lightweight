"""Create, sign, hash, and verify SentiChain transactions."""

import hashlib
import json
import math
import time
from typing import Any

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .keys import public_key_from_str, public_key_to_str


def _finite_number(value: Any) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)) or (
        isinstance(value, float) and math.isfinite(value)
    )


def _validate_fields(transaction: dict[str, Any]) -> None:
    for field in ("sender", "post_link", "matrix_signature"):
        if not isinstance(transaction.get(field), str) or not transaction[field]:
            raise ValueError(f"{field} must be a nonempty string.")
    if not isinstance(transaction.get("source"), str):
        raise ValueError("source must be a string containing the source text.")
    for field in ("post_timestamp", "transaction_timestamp"):
        if not _finite_number(transaction.get(field)):
            raise ValueError(f"{field} must be a finite number.")
    nonce = transaction.get("nonce")
    if not isinstance(nonce, int) or isinstance(nonce, bool):
        raise ValueError("nonce must be an integer.")
    matrix = transaction.get("post_matrix")
    if not isinstance(matrix, list) or not matrix:
        raise ValueError("post_matrix must be a nonempty list of numeric rows.")
    width = None
    for row in matrix:
        if not isinstance(row, list) or not row:
            raise ValueError("post_matrix rows must be nonempty lists.")
        if width is None:
            width = len(row)
        if len(row) != width or not all(_finite_number(value) for value in row):
            raise ValueError("post_matrix must be rectangular and contain finite numbers.")


def _json_object(transaction_json: str) -> dict[str, Any]:
    if not isinstance(transaction_json, str):
        raise ValueError("Transaction JSON must be a string.")
    try:
        transaction = json.loads(transaction_json)
        if not isinstance(transaction, dict):
            raise ValueError("Transaction JSON must contain an object.")
        json.dumps(transaction, sort_keys=True, allow_nan=False)
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise ValueError("Transaction JSON must contain an object with finite values.") from exc
    return transaction


def _canonical_bytes(transaction: dict[str, Any]) -> bytes:
    return json.dumps(transaction, sort_keys=True, allow_nan=False).encode("utf-8")


class Transaction:
    """A signed post and its embedding matrix.

    ``source`` contains the original source text. ``nonce`` is a caller supplied
    integer included in the signature; it does not by itself prevent replays.
    Timestamps are Unix seconds. Matrix rows contain finite numeric embeddings.
    """

    def __init__(
        self,
        sender: str,
        public_key: rsa.RSAPublicKey,
        post_timestamp: float,
        post_link: str,
        post_matrix: list[list[float]],
        matrix_signature: str,
        source: str,
        nonce: int = 1,
    ) -> None:
        self.sender = sender
        self.public_key = public_key
        self.post_timestamp = post_timestamp
        self.post_link = post_link
        self.post_matrix = post_matrix
        self.matrix_signature = matrix_signature
        self.source = source
        self.transaction_timestamp = time.time()
        self.nonce = nonce
        self.to_dict()

    def to_dict(self) -> dict[str, Any]:
        """Return validated transaction fields, excluding its signature."""
        transaction = {
            "sender": self.sender,
            "public_key": public_key_to_str(self.public_key),
            "post_timestamp": self.post_timestamp,
            "post_link": self.post_link,
            "post_matrix": self.post_matrix,
            "matrix_signature": self.matrix_signature,
            "source": self.source,
            "nonce": self.nonce,
            "transaction_timestamp": self.transaction_timestamp,
        }
        _validate_fields(transaction)
        return transaction

    def sign_transaction(self, private_key: rsa.RSAPrivateKey) -> bytes:
        """Sign the sorted JSON fields with RSA-PSS and SHA-256."""
        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise ValueError("private_key must be an RSA private key.")
        if private_key.public_key().public_numbers() != self.public_key.public_numbers():
            raise ValueError("The private key does not match the transaction public key.")
        return private_key.sign(
            _canonical_bytes(self.to_dict()),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )

    def serialize(self, signature: bytes) -> str:
        """Return sorted JSON with the supplied signature encoded as hex."""
        if not isinstance(signature, bytes) or not signature:
            raise ValueError("signature must be nonempty bytes.")
        transaction = self.to_dict()
        transaction["signature"] = signature.hex()
        return _canonical_bytes(transaction).decode("utf-8")


def generate_transaction_hash(transaction_json: str) -> str:
    """Hash sorted transaction JSON using SHA-256.

    Raise ``ValueError`` for invalid JSON, nonobject roots, or nonfinite values.
    This function hashes the supplied object without checking its signature.
    """
    try:
        return hashlib.sha256(_canonical_bytes(_json_object(transaction_json))).hexdigest()
    except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError) as exc:
        raise ValueError("Transaction JSON must contain an object with finite values.") from exc


def verify_signature(transaction_json: str) -> bool:
    """Return whether a transaction has valid fields and an RSA-PSS signature.

    Malformed JSON, unsupported keys, invalid field types, and invalid signatures
    return ``False``. No private key or source content is logged.
    """
    try:
        transaction = _json_object(transaction_json)
        signature_hex = transaction.pop("signature", None)
        if not isinstance(signature_hex, str) or not signature_hex:
            return False
        signature = bytes.fromhex(signature_hex)
        public_key = public_key_from_str(transaction.get("public_key"))
        _validate_fields(transaction)
        public_key.verify(
            signature,
            _canonical_bytes(transaction),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        return True
    except (
        InvalidSignature,
        UnsupportedAlgorithm,
        ValueError,
        TypeError,
        OverflowError,
        RecursionError,
        UnicodeError,
    ):
        return False
