"""Read public SentiChain matrices using Yototec Credits."""

import math
import time
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import requests

from .exceptions import (
    APIError,
    AuthenticationError,
    InsufficientCreditsError,
    RateLimitError,
    ResponseError,
    SentiChainError,
    TransportError,
)
from .matrices import is_matrix

BASE_URL = "https://api.sentichain.com"
Timeout = float | tuple[float, float]
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string.")
    return value


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer.")
    return value


def _number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number.")
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise ValueError(f"{name} must be a finite number.") from None
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        qualifier = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be a finite {qualifier} number.")
    return result


def _base_url(value: Any, name: str) -> str:
    _nonempty(value, name)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError(f"{name} must be an HTTP or HTTPS base URL.") from None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "?" in value
        or "#" in value
        or "\\" in value
        or any(character.isspace() or ord(character) < 32 for character in value)
        or (port is not None and not 0 < port <= 65535)
    ):
        raise ValueError(
            f"{name} must be an HTTP or HTTPS base URL without credentials, query or fragment."
        )
    return value.rstrip("/")


def _network(value: Any) -> str:
    if value not in ("mainnet", "testnet"):
        raise ValueError("network must be 'mainnet' or 'testnet'.")
    return value


def _timestamp(value: Any) -> str:
    _nonempty(value, "timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
    except ValueError:
        raise ValueError("timestamp must be an ISO 8601 timestamp with a timezone.") from None
    return value


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value)
        return seconds if math.isfinite(seconds) and seconds >= 0 else None
    except (ValueError, OverflowError):
        try:
            deadline = parsedate_to_datetime(value)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            return max(0.0, (deadline - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_time(value: Any) -> bool:
    try:
        return (
            not isinstance(value, bool)
            and isinstance(value, (float, int))
            and math.isfinite(value)
            and value >= 0
        )
    except OverflowError:
        return False


_BLOCK_FIELDS = frozenset({"block_number", "block_timestamp", "hash"})
_TRANSACTION_FIELDS = frozenset({"post_matrix", "matrix_signature"})


def _is_block(value: Any) -> bool:
    if (
        not isinstance(value, dict)
        or set(value) - (_BLOCK_FIELDS | {"transactions"})
        or not _is_count(value.get("block_number"))
        or not _is_time(value.get("block_timestamp"))
        or not isinstance(value.get("hash"), str)
        or not isinstance(value.get("transactions"), list)
    ):
        return False
    return all(
        isinstance(transaction, dict)
        and not (set(transaction) - _TRANSACTION_FIELDS)
        and is_matrix(transaction.get("post_matrix"))
        and (
            "matrix_signature" not in transaction
            or isinstance(transaction["matrix_signature"], str)
        )
        for transaction in value["transactions"]
    )


def _operation_id(value: str | None) -> str:
    if value is None:
        return str(uuid4())
    if not isinstance(value, str):
        raise ValueError("idempotency_key must be a UUID string.")
    try:
        operation = UUID(value)
    except ValueError:
        raise ValueError("idempotency_key must be a UUID string.") from None
    if str(operation) != value.lower():
        raise ValueError("idempotency_key must be a canonical UUID string.")
    return str(operation)


class Client:
    """Reuse connections and raise explicit errors for failed requests.

    Close the client when finished, or use it as a context manager. A block
    purchase returns complete matrices and block time, with no original source
    fields. Every automatic retry preserves that purchase's UUID.
    """

    def __init__(
        self,
        base_url: str = BASE_URL,
        api_key: str = "",
        timeout: Timeout = 30,
        *,
        max_retries: int = 2,
        backoff_factor: float = 0.5,
        max_backoff: float = 5.0,
    ):
        self.base_url = _base_url(base_url, "base_url")
        if not isinstance(api_key, str) or any(
            ord(character) < 33 or ord(character) > 126 for character in api_key
        ):
            raise ValueError("api_key must contain only visible ASCII characters.")
        self.api_key = api_key
        if isinstance(timeout, tuple):
            if len(timeout) != 2:
                raise ValueError("timeout must contain connect and read limits.")
            self.timeout: Timeout = (
                _number(timeout[0], "timeout", positive=True),
                _number(timeout[1], "timeout", positive=True),
            )
        else:
            self.timeout = _number(timeout, "timeout", positive=True)
        self.max_retries = _integer(max_retries, "max_retries")
        if self.max_retries > 5:
            raise ValueError("max_retries must be at most 5.")
        self.backoff_factor = _number(backoff_factor, "backoff_factor")
        self.max_backoff = _number(max_backoff, "max_backoff")
        self.last_operation_id: str | None = None
        self.credits_charged: int | None = None
        self.credits_remaining: int | None = None
        self._session = requests.Session()
        self._closed = False

    def close(self) -> None:
        """Release connections. Calling this more than once is safe."""
        if not self._closed:
            self._closed = True
            self._session.close()

    def __enter__(self) -> "Client":
        if self._closed:
            raise SentiChainError("Client is closed.")
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def _pause(self, attempt: int, retry_after: float | None = None) -> None:
        delay = retry_after if retry_after is not None else self.backoff_factor * (2**attempt)
        delay = min(self.max_backoff, delay)
        if delay:
            time.sleep(delay)

    def _get(
        self,
        path: str,
        params: dict[str, Any],
        field: str,
        valid: Callable[[Any], bool],
        *,
        paid: bool = False,
        idempotency_key: str | None = None,
    ) -> Any:
        if self._closed:
            raise SentiChainError("Client is closed.")
        headers = {"User-Agent": "SentiChain-Python-SDK/0.4"}
        operation_id = None
        if paid:
            if not self.api_key:
                raise AuthenticationError(401)
            operation_id = _operation_id(idempotency_key)
            self.last_operation_id = operation_id
            self.credits_charged = None
            self.credits_remaining = None
            headers.update(
                {
                    "Authorization": "Bearer " + self.api_key,
                    "Idempotency-Key": operation_id,
                }
            )
        for attempt in range(self.max_retries + 1):
            try:
                response = self._session.get(
                    self.base_url + path,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                    allow_redirects=False,
                )
            except requests.RequestException:
                if attempt < self.max_retries:
                    self._pause(attempt)
                    continue
                raise TransportError(
                    "The request could not be completed.", operation_id=operation_id
                ) from None
            try:
                status = response.status_code
                retry_after = _retry_after(response.headers.get("Retry-After"))
                retry = (
                    status in _RETRY_STATUSES
                    and attempt < self.max_retries
                    and (retry_after is None or retry_after <= self.max_backoff)
                )
                if not retry:
                    if status in (401, 403):
                        raise AuthenticationError(status, operation_id=operation_id)
                    if status == 402:
                        try:
                            error = response.json().get("error", {})
                            if not isinstance(error, dict):
                                error = {}
                        except (ValueError, AttributeError):
                            error = {}
                        raise InsufficientCreditsError(
                            required_credits=(
                                error.get("required_credits")
                                if _is_count(error.get("required_credits"))
                                else None
                            ),
                            available_credits=(
                                error.get("available_credits")
                                if _is_count(error.get("available_credits"))
                                else None
                            ),
                            operation_id=operation_id,
                        )
                    if status == 429:
                        raise RateLimitError(
                            status, retry_after=retry_after, operation_id=operation_id
                        )
                    if status != 200:
                        raise APIError(status, operation_id=operation_id)
                    try:
                        envelope = response.json()
                    except ValueError:
                        raise ResponseError("The response was not valid JSON.") from None
                    if not isinstance(envelope, dict) or field not in envelope:
                        raise ResponseError(f"The response did not contain '{field}'.")
                    result = envelope[field]
                    if result is not None and not valid(result):
                        raise ResponseError(f"The response contained an invalid '{field}' field.")
                    if paid:
                        for header, attribute in (
                            ("X-Yototec-Credits-Charged", "credits_charged"),
                            ("X-Yototec-Credits-Remaining", "credits_remaining"),
                        ):
                            value = response.headers.get(header, "")
                            if value.isascii() and value.isdigit() and len(value) <= 18:
                                setattr(self, attribute, int(value))
                    return result
            finally:
                response.close()
            self._pause(attempt, retry_after)
        raise SentiChainError("The request could not be completed.")

    def get_chain_length(self, network: str) -> int | None:
        """Return the number of blocks in the selected network."""
        return self._get(
            "/blockchain/get_chain_length",
            {"network": _network(network)},
            "chain_length",
            _is_count,
        )

    def get_last_block_time(self, network: str) -> float | None:
        """Return the latest block's Unix timestamp, or None for an empty chain."""
        return self._get(
            "/blockchain/get_last_block_time",
            {"network": _network(network)},
            "last_block_time",
            _is_time,
        )

    def get_total_number_of_transactions(self, network: str) -> int | None:
        """Return the confirmed transaction count."""
        return self._get(
            "/blockchain/get_total_number_of_transactions",
            {"network": _network(network)},
            "total_tx_count",
            _is_count,
        )

    def get_last_block(
        self,
        network: str,
        *,
        full_embedding: bool = True,
        idempotency_key: str | None = None,
    ) -> dict[str, Any] | None:
        """Purchase the latest block; automatic retries freeze the same purchase.

        ``full_embedding`` must be True. Pass an existing UUID only to resume
        the same intentional purchase, including an uncertain latest request.
        """
        if full_embedding is not True:
            raise ValueError("full_embedding must be True; public reads retain full matrices.")
        return self._get(
            "/blockchain/get_last_block",
            {"network": _network(network), "full_embedding": "true"},
            "block",
            _is_block,
            paid=True,
            idempotency_key=idempotency_key,
        )

    def get_block_by_number(
        self,
        network: str,
        block_number: int,
        *,
        full_embedding: bool = True,
        idempotency_key: str | None = None,
    ) -> dict[str, Any] | None:
        """Purchase one block's complete public matrices for one credit."""
        if full_embedding is not True:
            raise ValueError("full_embedding must be True; public reads retain full matrices.")
        return self._get(
            "/blockchain/get_block_by_number",
            {
                "network": _network(network),
                "block_number": _integer(block_number, "block_number"),
                "full_embedding": "true",
            },
            "block",
            _is_block,
            paid=True,
            idempotency_key=idempotency_key,
        )

    def get_block_number_from_timestamp(self, network: str, timestamp: str) -> int | None:
        """Return the last block at or before a timestamp with a timezone."""
        return self._get(
            "/blockchain/get_block_number_from_timestamp",
            {"network": _network(network), "timestamp": _timestamp(timestamp)},
            "block_number",
            _is_count,
        )

    def get_timestamp_from_block_number(self, network: str, block_number: int) -> str | None:
        """Return a block's ISO timestamp, or None if it does not exist."""
        return self._get(
            "/blockchain/get_timestamp_from_block_number",
            {"network": _network(network), "block_number": _integer(block_number, "block_number")},
            "timestamp",
            lambda value: isinstance(value, str),
        )

    def get_max_block_number(self) -> int | None:
        """Return the latest block represented in the event map."""
        return self._get("/mapper/get_max_block_number", {}, "max_block_number", _is_count)

    def get_vectorizer_public_key(self) -> str | None:
        """Read the vectorizer's public verification key without a purchase.

        Pin a trusted key separately when verifying authenticity, rather than
        treating a key fetched alongside a matrix as independent evidence.
        """
        return self._get(
            "/vectorizer/get_vectorizer_public_key",
            {},
            "public_key",
            lambda value: isinstance(value, str) and bool(value.strip()),
        )
