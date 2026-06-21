"""Shared API exception classes.

Extracted from shared/api_client.py so both RemnawaveApiClient and
BaseInternalApiClient can use the same error hierarchy without circular imports.
"""


class ApiClientError(Exception):
    """Generic API error with error code support."""

    def __init__(self, message: str = "", code: str = "ERR_API_000", hint: str = ""):
        self.message = message
        self.code = code
        self.hint = hint
        super().__init__(message)

    def __str__(self) -> str:
        return self.message or super().__str__()


class NotFoundError(ApiClientError):
    """404 error - resource not found."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, code="ERR_404_001", hint="Check if the resource exists")


class UnauthorizedError(ApiClientError):
    """401/403 error - authentication/authorization failed."""

    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, code="ERR_AUTH_001", hint="Check API token in settings")


class NetworkError(ApiClientError):
    """Network connectivity error."""

    def __init__(self, message: str = "Network error"):
        super().__init__(message, code="ERR_NET_001", hint="Check network connection and API server availability")


class TimeoutError(ApiClientError):
    """Request timeout error."""

    def __init__(self, message: str = "Request timeout"):
        super().__init__(message, code="ERR_TIMEOUT_001", hint="Server is slow or overloaded, try again later")


class RateLimitError(ApiClientError):
    """Rate limit exceeded error."""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, code="ERR_RATE_001", hint="Wait a moment before retrying")


class ServerError(ApiClientError):
    """Server error (5xx)."""

    def __init__(self, message: str = "Server error", status_code: int = 500):
        self.status_code = status_code
        code = f"ERR_SRV_{status_code}"
        super().__init__(message, code=code, hint="Server is temporarily unavailable")


class ValidationError(ApiClientError):
    """Data validation error."""

    def __init__(self, message: str = "Validation error", field: str = ""):
        self.field = field
        hint = f"Check value for field: {field}" if field else "Check input data format"
        super().__init__(message, code="ERR_VAL_001", hint=hint)
