"""
Vairified SDK Errors

Custom exception classes for API errors.
"""

from typing import Any, Optional


class VairifiedError(Exception):
    """
    Base exception for Vairified API errors.

    :ivar message: Error message.
    :ivar status_code: HTTP status code (if applicable).
    :ivar response: Raw response body (if available).
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response: Optional[Any] = None,
    ):
        """
        Initialize the error.

        :param message: Human-readable error message.
        :param status_code: HTTP status code.
        :param response: Raw response body.
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response = response

    def __str__(self) -> str:
        if self.status_code:
            return f"[{self.status_code}] {self.message}"
        return self.message


class RateLimitError(VairifiedError):
    """
    Raised when rate limit is exceeded.

    :ivar retry_after: Seconds to wait before retrying.
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        **kwargs,
    ):
        """
        Initialize rate limit error.

        :param message: Error message.
        :param retry_after: Seconds to wait before retrying.
        """
        super().__init__(message, status_code=429, **kwargs)
        self.retry_after = retry_after


class AuthenticationError(VairifiedError):
    """
    Raised when authentication fails.

    Typically means the API key is invalid or expired.
    """

    def __init__(self, message: str = "Invalid API key", **kwargs):
        """
        Initialize authentication error.

        :param message: Error message.
        """
        super().__init__(message, status_code=401, **kwargs)


class NotFoundError(VairifiedError):
    """
    Raised when a resource is not found.

    Typically means the requested member/player doesn't exist.
    """

    def __init__(self, message: str = "Resource not found", **kwargs):
        """
        Initialize not found error.

        :param message: Error message.
        """
        super().__init__(message, status_code=404, **kwargs)


class ValidationError(VairifiedError):
    """
    Raised when request validation fails.

    Check the response body for details on which fields failed validation.
    """

    def __init__(self, message: str = "Validation error", **kwargs):
        """
        Initialize validation error.

        :param message: Error message.
        """
        super().__init__(message, status_code=400, **kwargs)


class OAuthError(VairifiedError):
    """
    Raised when an OAuth operation fails.

    This can occur during authorization, token exchange, refresh, or revocation.

    :ivar error_code: OAuth error code (e.g., 'invalid_grant', 'expired_token').
    """

    def __init__(
        self,
        message: str = "OAuth error",
        error_code: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize OAuth error.

        :param message: Error message.
        :param error_code: OAuth error code.
        """
        super().__init__(message, **kwargs)
        self.error_code = error_code
