"""Custom exceptions for opencite."""

from __future__ import annotations


class OpenCiteError(Exception):
    """Base exception for all opencite errors."""

    def __init__(self, message: str, details: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        if self.details:
            return f"{self.message}\nDetails: {self.details}"
        return self.message


class ConfigurationError(OpenCiteError):
    """Missing or invalid configuration."""


class APIError(OpenCiteError):
    """Base for all API communication errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        cause: Exception | None = None,
        details: str | None = None,
    ):
        super().__init__(message, details)
        self.status_code = status_code
        self.cause = cause

    @classmethod
    def from_http_error(
        cls, error: Exception, status_code: int, description: str | None = None
    ) -> APIError:
        """Build the error for an HTTP failure.

        *description* replaces ``str(error)`` in the message; callers pass a
        redacted one so credentials in the request URL never reach messages.
        The raw *error* is then not kept as ``cause`` either, since its text
        still carries the unredacted URL.
        """
        text = description if description is not None else str(error)
        cause = error if description is None else None
        if status_code in (401, 403):
            return APIKeyError(text)
        if status_code == 429:
            return RateLimitError(cause=cause)
        return cls(f"HTTP {status_code}: {text}", status_code=status_code, cause=cause)


class APIKeyError(APIError):
    """Invalid or missing API key."""

    def __init__(self, message: str = "Invalid or missing API key"):
        super().__init__(
            message,
            details="Check that the required API key environment variable is set.",
        )


class RateLimitError(APIError):
    """Rate limit exceeded."""

    def __init__(
        self,
        retry_after: int | None = None,
        cause: Exception | None = None,
    ):
        message = "Rate limit exceeded"
        details = "Too many requests. The client will retry automatically."
        if retry_after:
            details += f" Retry after {retry_after}s."
        super().__init__(message, details=details, cause=cause)
        self.retry_after = retry_after


class SearchError(OpenCiteError):
    """Error during search operations."""


class PDFRetrievalError(OpenCiteError):
    """Failed to retrieve PDF."""


class ConversionError(OpenCiteError):
    """Failed to convert PDF to markdown."""


class IDConversionError(OpenCiteError):
    """Failed to convert between identifier types."""
