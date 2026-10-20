"""Exceptions raised by the HTTP client."""


class SentiChainError(Exception):
    """Base class for client errors."""


class APIError(SentiChainError):
    """An HTTP response reported a failed request."""

    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"The API returned HTTP {status_code}.")


class AuthenticationError(APIError):
    """The service rejected the supplied credentials or permissions."""


class RateLimitError(APIError):
    """The service limited requests, with an optional retry delay in seconds."""

    def __init__(self, status_code: int = 429, *, retry_after: float | None = None):
        self.retry_after = retry_after
        super().__init__(status_code)


class TransportError(SentiChainError):
    """A network or timeout error prevented completion."""


class ResponseError(SentiChainError):
    """The response could not be decoded as the expected result."""
