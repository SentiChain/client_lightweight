"""Read blockchain data and manage signed sentiment transactions."""

from importlib.metadata import version

from .client import Client
from .exceptions import (
    APIError,
    AuthenticationError,
    InsufficientCreditsError,
    RateLimitError,
    ResponseError,
    SentiChainError,
    TransportError,
)
from .matrices import verify_matrix_signature
from .transaction import Transaction, generate_transaction_hash, verify_signature

__version__ = version("sentichain")

__all__ = [
    "APIError",
    "AuthenticationError",
    "Client",
    "InsufficientCreditsError",
    "RateLimitError",
    "ResponseError",
    "SentiChainError",
    "Transaction",
    "TransportError",
    "generate_transaction_hash",
    "verify_signature",
    "verify_matrix_signature",
]
