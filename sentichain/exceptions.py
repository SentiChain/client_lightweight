"""Exceptions raised by the HTTP client."""


class SentiChainError(Exception):
    """Base class for client errors."""


class APIError(SentiChainError):
    """An HTTP response reported a failed request."""

    def __init__(self, status_code: int, *, operation_id: str | None = None):
        self.status_code = status_code
        self.operation_id = operation_id
        super().__init__(f"The API returned HTTP {status_code}.")


class AuthenticationError(APIError):
    """The service rejected the supplied credentials or permissions."""


class InsufficientCreditsError(APIError):
    """The entire purchase was rejected without data or a debit."""

    def __init__(
        self,
        *,
        required_credits: int | None = None,
        available_credits: int | None = None,
        operation_id: str | None = None,
    ):
        self.required_credits = required_credits
        self.available_credits = available_credits
        super().__init__(402, operation_id=operation_id)


class RateLimitError(APIError):
    """The service limited requests, with an optional retry delay in seconds."""

    def __init__(
        self,
        status_code: int = 429,
        *,
        retry_after: float | None = None,
        operation_id: str | None = None,
    ):
        self.retry_after = retry_after
        super().__init__(status_code, operation_id=operation_id)


class TransportError(SentiChainError):
    """A network or timeout error prevented completion."""

    def __init__(self, message: str, *, operation_id: str | None = None):
        self.operation_id = operation_id
        super().__init__(message)


class ResponseError(SentiChainError):
    """The response could not be decoded as the expected result."""
