"""Read blockchain data, event maps and market analysis."""

import math
import time
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

import requests

from .exceptions import (
    APIError,
    AuthenticationError,
    RateLimitError,
    ResponseError,
    SentiChainError,
    TransportError,
)

BASE_URL = "https://api.sentichain.com"
ANALYTICS_BASE_URL = "https://api.sentimove.com"
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


def _is_user(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and all(isinstance(value.get(field), str) for field in ("user_id", "name", "email"))
        and _is_count(value.get("points"))
    )


def _is_block(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and _is_count(value.get("block_number"))
        and _is_time(value.get("block_timestamp"))
        and all(
            isinstance(value.get(field), str)
            for field in ("previous_hash", "hash", "validator", "consensus_root")
        )
        and isinstance(value.get("transactions"), dict)
        and all(
            isinstance(key, str) and isinstance(transaction, dict)
            for key, transaction in value["transactions"].items()
        )
    )


def _is_points(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(row, (dict, list)) for row in value)


class Client:
    """Reuse connections and raise explicit errors for failed requests.

    Close the client when finished, or use it as a context manager. Block reads
    request complete matrices; field visibility still depends on credentials.
    Analysis requests use ``analytics_base_url`` without the SentiChain API key.
    """

    def __init__(
        self,
        base_url: str = BASE_URL,
        api_key: str = "",
        timeout: Timeout = 30,
        *,
        analytics_base_url: str = ANALYTICS_BASE_URL,
        max_retries: int = 2,
        backoff_factor: float = 0.5,
        max_backoff: float = 5.0,
    ):
        self.base_url = _base_url(base_url, "base_url")
        self.analytics_base_url = _base_url(analytics_base_url, "analytics_base_url")
        if not isinstance(api_key, str):
            raise ValueError("api_key must be a string.")
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
        analytics: bool = False,
    ) -> Any:
        if self._closed:
            raise SentiChainError("Client is closed.")
        base_url = self.analytics_base_url if analytics else self.base_url
        for attempt in range(self.max_retries + 1):
            try:
                response = self._session.get(
                    base_url + path,
                    params=params,
                    timeout=self.timeout,
                    allow_redirects=False,
                )
            except requests.RequestException:
                if attempt < self.max_retries:
                    self._pause(attempt)
                    continue
                raise TransportError("The request could not be completed.") from None
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
                        raise AuthenticationError(status)
                    if status == 429:
                        raise RateLimitError(status, retry_after=retry_after)
                    if status != 200:
                        raise APIError(status)
                    try:
                        envelope = response.json()
                    except ValueError:
                        raise ResponseError("The response was not valid JSON.") from None
                    if not isinstance(envelope, dict) or field not in envelope:
                        raise ResponseError(f"The response did not contain '{field}'.")
                    result = envelope[field]
                    if result is not None and not valid(result):
                        raise ResponseError(f"The response contained an invalid '{field}' field.")
                    return result
            finally:
                response.close()
            self._pause(attempt, retry_after)
        raise SentiChainError("The request could not be completed.")

    def get_user_info(self, user_id: str, api_key: str | None = None) -> dict[str, Any] | None:
        """Return account details using the configured key unless overridden."""
        key = self.api_key if api_key is None else api_key
        if not isinstance(key, str):
            raise ValueError("api_key must be a string.")
        return self._get(
            "/api/get_user_info",
            {"user_id": _nonempty(user_id, "user_id"), "api_key": key},
            "user",
            _is_user,
        )

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

    def get_last_block(self, network: str, *, full_embedding: bool = True) -> dict[str, Any] | None:
        """Return the latest block. Credentials determine field visibility."""
        if not isinstance(full_embedding, bool):
            raise ValueError("full_embedding must be a boolean.")
        params = {"network": _network(network), "api_key": self.api_key}
        if full_embedding:
            params["full_embedding"] = "true"
        return self._get("/blockchain/get_last_block", params, "block", _is_block)

    def get_block_by_number(
        self,
        network: str,
        block_number: int,
        *,
        full_embedding: bool = True,
    ) -> dict[str, Any] | None:
        """Return a block by height. Credentials determine field visibility."""
        if not isinstance(full_embedding, bool):
            raise ValueError("full_embedding must be a boolean.")
        params = {
            "network": _network(network),
            "block_number": _integer(block_number, "block_number"),
            "api_key": self.api_key,
        }
        if full_embedding:
            params["full_embedding"] = "true"
        return self._get("/blockchain/get_block_by_number", params, "block", _is_block)

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

    def get_points_by_block_no_embedding(self, block_number: int) -> list[Any] | None:
        """Return event map rows without embeddings for one block."""
        return self._get(
            "/mapper/get_points_by_block_no_embedding",
            {"block_number": _integer(block_number, "block_number"), "api_key": self.api_key},
            "points",
            _is_points,
        )

    def get_points_by_block_range_no_embedding(
        self,
        start_block: int,
        end_block: int,
    ) -> list[Any] | None:
        """Return event map rows for an inclusive block range."""
        _integer(start_block, "start_block")
        _integer(end_block, "end_block")
        if end_block < start_block:
            raise ValueError("end_block must be at least start_block.")
        return self._get(
            "/mapper/get_points_by_block_range_no_embedding",
            {"start_block": start_block, "end_block": end_block, "api_key": self.api_key},
            "points",
            _is_points,
        )

    def get_reasoning_match_chunk_end(
        self,
        ticker: str,
        summary_type: str,
        user_chunk_end: int,
    ) -> str | None:
        """Return matching analysis without sending the SentiChain API key."""
        return self._get(
            "/agent/get_reasoning_match_chunk_end",
            {
                "ticker": _nonempty(ticker, "ticker"),
                "summary_type": _nonempty(summary_type, "summary_type"),
                "user_chunk_end": _integer(user_chunk_end, "user_chunk_end"),
            },
            "reasoning",
            lambda value: isinstance(value, str),
            analytics=True,
        )
