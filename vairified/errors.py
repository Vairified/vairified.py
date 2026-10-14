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


class ServiceUnavailableError(VairifiedError):
    """
    Raised on HTTP 503 -- the API is temporarily refusing this request.

    The SDK never retries on its own. A 503 is safe to retry later, but wait at
    least :attr:`retry_after` seconds first: retrying in a tight loop only adds
    load to a service that has said it is not taking the request.

    :ivar retry_after: Seconds to wait before retrying, from the ``Retry-After``
        header (or the body's ``retryAfter`` when the header is missing), or
        ``None`` if the server didn't say.
    """

    def __init__(
        self,
        message: str = "Service unavailable",
        retry_after: Optional[int] = None,
        **kwargs,
    ):
        """
        Initialize service unavailable error.

        :param message: Error message.
        :param retry_after: Seconds to wait before retrying.
        """
        super().__init__(message, status_code=503, **kwargs)
        self.retry_after = retry_after


class ScoreEntryPausedError(ServiceUnavailableError):
    """
    Raised on HTTP 503 with code ``SCORE_ENTRY_PAUSED``.

    Vairified has paused score entry for a rating maintenance window. Only writes
    that create or re-rate matches are refused (``matches.submit()``,
    ``matches.tournament_import()``); reads keep working.

    Nothing was saved. Resubmit the same payload after :attr:`retry_after`
    seconds (the API currently asks for 300). The SDK does not retry for you.

    :ivar code: Always ``"SCORE_ENTRY_PAUSED"``.
    """

    code = "SCORE_ENTRY_PAUSED"

    def __init__(
        self,
        message: str = "Score entry is paused for maintenance",
        retry_after: Optional[int] = None,
        **kwargs,
    ):
        """
        Initialize score entry paused error.

        :param message: Error message.
        :param retry_after: Seconds to wait before resubmitting.
        """
        super().__init__(message, retry_after=retry_after, **kwargs)


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


class PermissionDeniedError(VairifiedError):
    """
    Raised on HTTP 403 -- the API key is valid but not allowed to do this.

    It lacks the scope the route needs (e.g. ``leaderboard:read``), the player
    has not connected to your app, or the key's IP allow-list refuses the caller.
    """

    def __init__(self, message: str = "Permission denied", **kwargs):
        """
        Initialize permission denied error.

        :param message: Error message.
        """
        super().__init__(message, status_code=403, **kwargs)


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
