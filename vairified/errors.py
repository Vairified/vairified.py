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


class WebhookSignatureError(VairifiedError):
    """
    Raised when a webhook delivery cannot be trusted.

    :rotating_light: **The message never contains the signing secret, the received
    digest, or the computed one.** Writing either digest into an error puts a valid
    HMAC of the partner's own payload into their application logs, where it is an
    oracle for anyone who can read them. Branch on :attr:`reason`; there is
    deliberately nothing finer-grained to log.

    :ivar reason: Why it was refused. One of:

        ``no_secret_configured``
            No usable signing secret was supplied. This is **your** configuration,
            not an attack -- almost always an unset environment variable. Separate
            from ``signature_mismatch`` on purpose: reporting a missing secret as a
            mismatch sends people hunting an attacker when the fix is one env var.
        ``invalid_option``
            A caller-supplied option was not usable -- a non-numeric or negative
            tolerance, a NaN clock. Separate from ``timestamp_out_of_tolerance``
            for the same reason: that one means "this delivery's clock disagrees
            with yours", and reporting your own typo under it sends people hunting
            clock skew on a healthy box.
        ``missing_signature``
            No ``X-Vairified-Signature`` header at all.
        ``malformed_signature``
            Present but unparseable, or missing its ``t`` / ``v1`` parts.
        ``timestamp_out_of_tolerance``
            Outside the replay window, in either direction.
        ``signature_mismatch``
            Parsed fine; no supplied secret produces this digest.
        ``malformed_body``
            Verified, but the body is not JSON, or is not a webhook envelope, or a
            field the caller will read is absent or the wrong type.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
