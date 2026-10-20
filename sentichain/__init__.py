"""Read blockchain data and manage signed sentiment transactions."""

from importlib.metadata import version

from .client import Client
from .exceptions import (
    APIError,
    AuthenticationError,
    RateLimitError,
    ResponseError,
    SentiChainError,
    TransportError,
)
from .transaction import Transaction, generate_transaction_hash, verify_signature

__version__ = version("sentichain")

__all__ = [
    "APIError",
    "AuthenticationError",
    "Client",
    "RateLimitError",
    "ResponseError",
    "SentiChainError",
    "Transaction",
    "TransportError",
    "generate_transaction_hash",
    "verify_signature",
]
