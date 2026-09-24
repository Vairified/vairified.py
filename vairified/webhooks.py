"""
Webhook signature verification.

Standalone on purpose -- a webhook receiver is an inbound HTTP handler. It usually
holds no API key, may never call the Partner API, and should not have to construct
a client just to check a signature.

Mirrors ``verifyWebhook`` in the TypeScript SDK exactly in behaviour. The one
deliberate difference is that this function is **synchronous**: Python's ``hmac``
is a sync stdlib module, while the browser-portable Web Crypto API the JS SDK uses
is async. Forcing either to match the other would be worse than the asymmetry.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import time
from collections.abc import Sequence
from typing import TypeGuard

from pydantic import ValidationError

from .errors import WebhookSignatureError
from .webhook_models import (
    ConnectionRevokedEvent,
    EventCreatedEvent,
    MemberStatusEvent,
    RatingUpdatedEvent,
    UnknownWebhookEvent,
    VerifiedWebhookEvent,
)

__all__ = [
    "DEFAULT_TOLERANCE_SECONDS",
    "is_connection_revoked_event",
    "is_event_created_event",
    "is_member_status_event",
    "is_rating_updated_event",
    "verify_webhook",
]

DEFAULT_TOLERANCE_SECONDS = 300
"""How far apart the delivery's timestamp and your clock may be, in seconds.

Five minutes, matching the scheme this signature format follows. The window is
what stops a captured delivery being replayed indefinitely -- without it a valid
signature stays valid forever.
"""

SIGNATURE_HEADER = "X-Vairified-Signature"

_MAX_SIGNATURE_HEX = 64
"""A SHA-256 digest is 32 bytes; nothing longer can ever match one. Capped before
the hex decode so a multi-megabyte ``v1`` cannot make us allocate on every
request."""

_EVENT_MODELS: dict[str, type] = {
    "member.status": MemberStatusEvent,
    "connection.revoked": ConnectionRevokedEvent,
    "rating.updated": RatingUpdatedEvent,
    "event.created": EventCreatedEvent,
}


def _parse_signature_header(header: str) -> tuple[int, str, str]:
    """Return ``(timestamp, raw_timestamp, signature)``.

    Deliberately tolerant of shape and strict about content: pairs may arrive in
    any order and unknown keys are ignored, so adding a ``v2=`` later cannot break
    a receiver built today. What is *not* tolerated is a missing ``t`` or ``v1``.

    ``raw_timestamp`` is the value exactly as transmitted, because the HMAC is
    built from that rather than from the re-stringified integer -- ``t=017`` and
    ``t=17`` are different bytes, and signing the normalised form would let both
    verify against one digest.
    """
    timestamp: int | None = None
    raw_timestamp: str | None = None
    signature: str | None = None

    for part in header.split(","):
        key, sep, value = part.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if key == "t" and timestamp is None:
            # Reject anything that is not a plain integer. `int()` would happily
            # accept ' 12 ', '+12' and '1_2'.
            # `isascii()` is load-bearing: `str.isdigit()` is True for
            # superscripts and other Unicode digit forms that `int()` then
            # refuses, so without it a crafted header escapes as a raw
            # ValueError rather than our own error -- past the handler this
            # function's own docstring tells partners to write.
            if not (value.isascii() and value.isdigit()):
                raise WebhookSignatureError(
                    "malformed_signature",
                    f"{SIGNATURE_HEADER} carried a timestamp that is not an integer",
                )
            timestamp = int(value)
            raw_timestamp = value
        elif key == "v1" and signature is None:
            signature = value

    if timestamp is None or raw_timestamp is None or signature is None:
        raise WebhookSignatureError(
            "malformed_signature",
            f"{SIGNATURE_HEADER} must carry both a 't' and a 'v1' part",
        )
    return timestamp, raw_timestamp, signature


def _hex_to_bytes(value: str) -> bytes:
    """Decode a hex digest, case-insensitively.

    The API emits lowercase today, and a case-sensitive comparison would be
    correct right up until it wasn't.
    """
    if len(value) > _MAX_SIGNATURE_HEX:
        raise WebhookSignatureError(
            "malformed_signature",
            f"{SIGNATURE_HEADER} carried a 'v1' value longer than a SHA-256 digest",
        )
    if not value or len(value) % 2:
        raise WebhookSignatureError(
            "malformed_signature",
            f"{SIGNATURE_HEADER} carried a 'v1' value that is not a hex digest",
        )
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise WebhookSignatureError(
            "malformed_signature",
            f"{SIGNATURE_HEADER} carried a 'v1' value that is not a hex digest",
        ) from exc


def verify_webhook(
    raw_body: bytes | str,
    signature_header: str | None,
    secret: str | None | Sequence[str | None],
    *,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now_seconds: float | None = None,
) -> VerifiedWebhookEvent:
    """Verify a webhook delivery and return it typed.

    :param raw_body: The **exact bytes** of the request body. This is the part
        people get wrong: the signature covers what was sent, so a body that has
        been parsed and re-serialised (FastAPI's parsed body, ``request.json()``)
        produces different bytes and every signature fails. Capture the raw body.
    :param signature_header: The ``X-Vairified-Signature`` header value.
    :param secret: Your webhook signing secret, or **several**. Pass both the old
        and the new around a rotation: deliveries already queued were signed with
        the old secret and keep arriving for hours afterwards, so a verifier that
        knows only the new one discards them.
    :param tolerance_seconds: Clock-skew allowance, applied in **both**
        directions -- a delivery dated too far in the future is refused exactly as
        a stale one is. A one-sided check would accept a forged future timestamp
        forever, which is the replay hole the window exists to close.
    :param now_seconds: Current epoch seconds. Injectable for tests; you should
        not need it in production.
    :raises WebhookSignatureError: for **every** refusal. Read ``.reason``.

    :rotating_light: **Deduplicate on the body's** ``event_id``, never on the
    ``X-Vairified-Event-Id`` header -- that header is outside the signature, so an
    attacker replaying a captured delivery inside the tolerance window can change
    it freely. Replay inside the window is otherwise unprevented by design: the
    timestamp tolerance is the only replay control this function applies, so your
    own deduplication is what stops a delivery being applied twice.

    .. code-block:: python

        from vairified import verify_webhook, is_member_status_event
        from vairified.errors import WebhookSignatureError

        @app.post("/hooks/vair")
        async def hook(request: Request):
            try:
                event = verify_webhook(
                    await request.body(),            # the raw bytes
                    request.headers.get("X-Vairified-Signature"),
                    [os.environ.get("VAIR_WEBHOOK_SECRET"),
                     os.environ.get("VAIR_WEBHOOK_SECRET_PREVIOUS")],
                )
            except WebhookSignatureError:
                return Response(status_code=400)
            if is_member_status_event(event):
                print(event.data.member_id, event.data.is_vair_plus)
            return Response(status_code=204)
    """
    # Validated BEFORE anything else, and never allowed to escape as a TypeError.
    # The common single-secret call passes `os.environ.get(...)` straight through,
    # and with the variable unset that is `None`. A missing secret is *your*
    # configuration, not an attack, and gets its own reason so nobody goes hunting
    # an attacker when the fix is one environment variable.
    candidates: Sequence[str | None]
    if secret is None or isinstance(secret, str):
        candidates = [secret]
    else:
        candidates = list(secret)
    # `strip()` first: a whitespace-only secret passes a bare length check and is
    # then reported as a signature mismatch, i.e. as an attack.
    secrets = [s for s in candidates if isinstance(s, str) and s.strip()]
    if not secrets:
        raise WebhookSignatureError(
            "no_secret_configured", "No usable signing secret was supplied"
        )

    if not signature_header:
        raise WebhookSignatureError(
            "missing_signature", f"No {SIGNATURE_HEADER} header was supplied"
        )

    # A non-finite or negative window would disable the check rather than narrow
    # it. Refuse instead of falling back to a default: a caller who passed a bad
    # value should find out, not be quietly corrected.
    if not isinstance(tolerance_seconds, (int, float)) or isinstance(
        tolerance_seconds, bool
    ):
        raise WebhookSignatureError(
            "invalid_option", "tolerance_seconds must be a number"
        )
    # `isfinite` catches infinity as well as NaN. An infinite window is
    # accepted by a naive NaN check and silently disables replay protection
    # entirely -- measured, a delivery 31 years stale verified.
    if not math.isfinite(tolerance_seconds) or tolerance_seconds < 0:
        raise WebhookSignatureError(
            "invalid_option", "tolerance_seconds must be a finite, non-negative number"
        )
    now = time.time() if now_seconds is None else now_seconds
    if now != now:  # NaN
        raise WebhookSignatureError(
            "invalid_option", "now_seconds must be a finite number"
        )

    timestamp, raw_timestamp, signature = _parse_signature_header(signature_header)

    # Window check BEFORE the hex decode: it is the cheap test, so a garbage `v1`
    # never reaches an allocation. Two-sided -- a future-dated delivery is as
    # refused as a stale one.
    if abs(now - timestamp) > tolerance_seconds:
        raise WebhookSignatureError(
            "timestamp_out_of_tolerance",
            f"The delivery timestamp is outside the {tolerance_seconds}s tolerance",
        )

    signature_bytes = _hex_to_bytes(signature)

    body_bytes = (
        raw_body.encode("utf-8") if isinstance(raw_body, str) else bytes(raw_body)
    )
    signed = raw_timestamp.encode("ascii") + b"." + body_bytes

    # `compare_digest` rather than `==`: a plain comparison short-circuits on the
    # first differing byte and leaks how much of a forged digest was correct.
    # Deliberately no early exit across candidates either.
    matched = False
    for candidate in secrets:
        expected = hmac.new(candidate.encode("utf-8"), signed, hashlib.sha256).digest()
        matched = hmac.compare_digest(expected, signature_bytes) or matched

    if not matched:
        raise WebhookSignatureError(
            "signature_mismatch",
            "The webhook signature did not match any supplied secret",
        )

    try:
        parsed = json.loads(signed[len(raw_timestamp) + 1 :].decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise WebhookSignatureError(
            "malformed_body", "The webhook body is not valid JSON"
        ) from exc

    if not isinstance(parsed, dict):
        raise WebhookSignatureError(
            "malformed_body", "The webhook body is not a JSON object"
        )

    event_type = parsed.get("event")
    model = _EVENT_MODELS.get(event_type) if isinstance(event_type, str) else None

    # :rotating_light: pydantic's ValidationError is re-raised as ours.
    #
    # The TypeScript SDK raises `WebhookSignatureError` with `reason:
    # 'malformed_body'`; letting pydantic's own error escape here would mean the
    # two SDKs fail with different exception classes, different attributes and no
    # `reason` on one side -- the exact parity defect this leg exists to close, and
    # the single highest-risk thing about mirroring a TypeScript verifier in
    # pydantic, whose default behaviour is *almost* right.
    try:
        if model is None:
            return UnknownWebhookEvent.model_validate(parsed)
        return model.model_validate(parsed)  # type: ignore[no-any-return]
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(p) for p in first["loc"])
        if not isinstance(event_type, str):
            # Matches the TypeScript wording for an envelope-level failure. The
            # old text read "A 'None' event is missing ...", which is a confusing
            # string to leave in a partner's logs.
            message = f"The webhook body is missing a string '{field}'"
        else:
            message = f"A '{event_type}' event is missing a valid '{field}'"
        raise WebhookSignatureError("malformed_body", message) from exc


def is_member_status_event(event: VerifiedWebhookEvent) -> TypeGuard[MemberStatusEvent]:
    """Narrow a verified event to ``member.status``."""
    return isinstance(event, MemberStatusEvent)


def is_connection_revoked_event(
    event: VerifiedWebhookEvent,
) -> TypeGuard[ConnectionRevokedEvent]:
    """Narrow a verified event to ``connection.revoked``.

    :rotating_light: ``data.reason`` is an open set -- ``player_deleted`` and
    ``player_disconnected`` today, more later. Never branch on it exhaustively.
    """
    return isinstance(event, ConnectionRevokedEvent)


def is_rating_updated_event(
    event: VerifiedWebhookEvent,
) -> TypeGuard[RatingUpdatedEvent]:
    """Narrow a verified event to ``rating.updated`` -- the event that makes up
    almost all real traffic.

    Its ``data`` is the multi-sport **snapshot**, not the polling model.
    """
    return isinstance(event, RatingUpdatedEvent)


def is_event_created_event(event: VerifiedWebhookEvent) -> TypeGuard[EventCreatedEvent]:
    """Narrow a verified event to ``event.created``.

    :rotating_light: ``data.event_id`` is an **int** and is not the envelope's
    string ``event_id``. Deduplicate on the envelope's; refer to the event by
    ``data``'s.
    """
    return isinstance(event, EventCreatedEvent)
