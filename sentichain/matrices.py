"""Validate and verify the restricted public matrix representation."""

import json
import math
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def _finite(value: Any) -> bool:
    try:
        return (
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        )
    except OverflowError:
        return False


def is_matrix(matrix: Any) -> bool:
    """Whether a value is a complete nonempty rectangular finite matrix."""
    return (
        isinstance(matrix, list)
        and bool(matrix)
        and isinstance(matrix[0], list)
        and bool(matrix[0])
        and all(
            isinstance(row, list)
            and len(row) == len(matrix[0])
            and all(_finite(value) for value in row)
            for row in matrix
        )
    )


def verify_matrix_signature(
    matrix: list[list[float]], signature: str, public_key: rsa.RSAPublicKey
) -> bool:
    """Check a hex matrix proof against a separately trusted vectorizer key.

    This authenticates the exact JSON matrix bytes signed by the vectorizer.
    It does not verify the omitted canonical transaction, its hash/signature,
    the block's hash, original source text or inclusion in a block.
    """
    if not is_matrix(matrix) or not isinstance(signature, str):
        return False
    if not isinstance(public_key, rsa.RSAPublicKey):
        return False
    try:
        public_key.verify(
            bytes.fromhex(signature),
            json.dumps(matrix, allow_nan=False).encode("utf-8"),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
    except (InvalidSignature, ValueError, TypeError, OverflowError):
        return False
    return True
