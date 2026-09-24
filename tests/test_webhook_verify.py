"""
Webhook signature verification -- Vairified#1275.

Mirrors ``tests/webhook-verify.test.ts`` in the TypeScript SDK row for row. Where
the two differ it is because the languages differ, never because the behaviour
does -- and each such place says so.
"""

import hashlib
import hmac

import pytest

from vairified import (
    DEFAULT_TOLERANCE_SECONDS,
    is_connection_revoked_event,
    is_event_created_event,
    is_member_status_event,
    is_rating_updated_event,
    verify_webhook,
)
from vairified.errors import WebhookSignatureError

# ---------------------------------------------------------------------------
# The shared golden vector
# ---------------------------------------------------------------------------
#
# Generated ONCE from the backend's own signing path and pasted here as
# literals. It is NOT computed by this SDK, on purpose: a vector this package
# derived would only prove the package agrees with itself.
#
# These are the SAME literals asserted in vairified.js's webhook-verify test.
# That byte-for-byte agreement is the only artifact in either repo that
# *measures* parity instead of re-reasoning it -- if the two implementations
# ever diverge on encoding, hex case or payload construction, this is what goes
# red. Do not regenerate it in one repo without regenerating it in the other.
#
# The body carries two things deliberately: non-ASCII characters, and NO
# ``sports`` key (the member-declined-rating-scope cohort, which production has
# none of today).
GOLDEN_SECRET = "whsec_golden_vector_do_not_use_in_production"
GOLDEN_TIMESTAMP = 1758700000
GOLDEN_HEADER = (
    "t=1758700000,v1=bb0909efd0c4aa80d22af4c8bfd0cc1d2482acf1a2e5d6ddc99bb94e7fb653d7"
)
GOLDEN_BODY = (
    '{"event":"member.status","eventId":"evt_0000000000000000000000000000abcd",'
    '"timestamp":"2026-09-24T12:00:00.000Z","data":{"memberId":7204743,'
    '"isVairPlus":true,"isAmbassador":false,"vairProStatus":null,'
    '"vairifiedRatingStatus":"COMPLETED","changedAt":"2026-09-24T12:00:00.000Z",'
    '"displayName":"Renée Ōsaka-Müller ✓"}}'
)

NOW = GOLDEN_TIMESTAMP


def sign(body: str, secret: str, timestamp: int) -> str:
    """Sign a body the way the backend does, for cases the vector doesn't cover."""
    digest = hmac.new(
        secret.encode("utf-8"), f"{timestamp}.{body}".encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def expect_rejection(reason: str, **kwargs) -> WebhookSignatureError:
    with pytest.raises(WebhookSignatureError) as exc:
        verify_webhook(**kwargs)
    assert exc.value.reason == reason
    return exc.value


# ---------------------------------------------------------------------------
# The golden vector
# ---------------------------------------------------------------------------


# mutation-checked 2026-09-24: changed the signed-payload separator from "." to
# ":" in webhooks.py -> all 4 of these red (21 across the file). That mutant is
# the right one here: these are positive tests, so forcing the HMAC comparison
# to pass leaves them green -- it is the PAYLOAD CONSTRUCTION they are
# load-bearing on, and the JS suite records the same mutant for the same rows.
class TestGoldenVector:
    def test_verifies_the_backend_generated_vector(self):
        event = verify_webhook(
            GOLDEN_BODY, GOLDEN_HEADER, GOLDEN_SECRET, now_seconds=NOW
        )
        assert event.event == "member.status"
        assert event.event_id == "evt_0000000000000000000000000000abcd"

    def test_verifies_the_same_vector_as_bytes(self):
        event = verify_webhook(
            GOLDEN_BODY.encode("utf-8"), GOLDEN_HEADER, GOLDEN_SECRET, now_seconds=NOW
        )
        assert event.event == "member.status"

    def test_member_id_is_an_int_and_no_uuid_is_exposed(self):
        import json
        import re

        event = verify_webhook(
            GOLDEN_BODY, GOLDEN_HEADER, GOLDEN_SECRET, now_seconds=NOW
        )
        assert is_member_status_event(event)
        assert isinstance(event.data.member_id, int)
        # Scoped to `data`, not the whole event: the envelope's event id is a
        # random delivery id and is not an internal identifier.
        assert not re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            json.dumps(event.data.model_dump()),
            re.I,
        )

    def test_absent_sports_stays_absent_never_empty(self):
        # "We were not permitted to tell you" must stay distinguishable from
        # "holds no certifications". Defaulting to {} silently turns the first
        # into the second -- which is what this repo's own convention for
        # per-sport maps would have done.
        event = verify_webhook(
            GOLDEN_BODY, GOLDEN_HEADER, GOLDEN_SECRET, now_seconds=NOW
        )
        assert is_member_status_event(event)
        assert event.data.sports is None
        # The JS side asserts the KEY is missing; here the idiomatic pair is
        # `None`. Both satisfy the same rule, and this pins the wire shape so a
        # doc example cannot publish `"sports": null`.
        assert "sports" not in event.data.model_dump(exclude_unset=True)


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


# mutation-checked 2026-09-24: forced `matched = True` in the secrets loop ->
# 4 red -- the three below that assert a refusal (tampered body, the message-leak
# check, the rotation none-match case) plus the constant-time source check, which
# reds because the mutant deletes the compare_digest call it greps for.
class TestRefusals:
    def test_refuses_a_body_altered_by_one_byte(self):
        tampered = GOLDEN_BODY.replace('"isVairPlus":true', '"isVairPlus":fals') + "e"
        expect_rejection(
            "signature_mismatch",
            raw_body=tampered,
            signature_header=GOLDEN_HEADER,
            secret=GOLDEN_SECRET,
            now_seconds=NOW,
        )

    @pytest.mark.parametrize("header", [None, ""])
    def test_refuses_a_missing_header(self, header):
        expect_rejection(
            "missing_signature",
            raw_body=GOLDEN_BODY,
            signature_header=header,
            secret=GOLDEN_SECRET,
            now_seconds=NOW,
        )

    def test_refuses_a_header_missing_t_or_v1(self):
        digest = GOLDEN_HEADER.split("v1=")[1]
        for header in (f"v1={digest}", f"t={GOLDEN_TIMESTAMP}", "total nonsense"):
            expect_rejection(
                "malformed_signature",
                raw_body=GOLDEN_BODY,
                signature_header=header,
                secret=GOLDEN_SECRET,
                now_seconds=NOW,
            )

    # mutation-checked 2026-09-24: replaced `value.isdigit()` with `True` ->
    # 1 red, exactly this test.
    def test_refuses_a_non_integer_timestamp(self):
        # Both SDKs strip() the value before the digit check, so whitespace
        # padding is accepted in each -- identically. What neither accepts is a
        # value that is not a plain integer.
        digest = GOLDEN_HEADER.split("v1=")[1]
        expect_rejection(
            "malformed_signature",
            raw_body=GOLDEN_BODY,
            signature_header=f"t=1.7587e9,v1={digest}",
            secret=GOLDEN_SECRET,
            now_seconds=NOW,
        )

    def test_accepts_pairs_in_any_order_and_ignores_unknown_keys(self):
        digest = GOLDEN_HEADER.split("v1=")[1]
        # A future `v2=` must not break a receiver written today.
        header = f"v2=deadbeef,v1={digest},t={GOLDEN_TIMESTAMP}"
        assert (
            verify_webhook(GOLDEN_BODY, header, GOLDEN_SECRET, now_seconds=NOW).event
            == "member.status"
        )

    # mutation-checked 2026-09-24: made _hex_to_bytes reject A-F -> 1 red,
    # exactly this test.
    def test_compares_the_digest_case_insensitively(self):
        digest = GOLDEN_HEADER.split("v1=")[1]
        header = f"t={GOLDEN_TIMESTAMP},v1={digest.upper()}"
        assert (
            verify_webhook(GOLDEN_BODY, header, GOLDEN_SECRET, now_seconds=NOW).event
            == "member.status"
        )

    def test_never_names_the_secret_or_either_digest(self):
        import re

        err = expect_rejection(
            "signature_mismatch",
            raw_body=GOLDEN_BODY,
            signature_header=GOLDEN_HEADER,
            secret="the-wrong-secret",
            now_seconds=NOW,
        )
        digest = GOLDEN_HEADER.split("v1=")[1]
        assert "the-wrong-secret" not in str(err)
        assert digest not in str(err)
        assert not re.search(r"[0-9a-f]{32}", str(err), re.I)

    def test_refuses_an_oversized_signature_cheaply(self):
        expect_rejection(
            "malformed_signature",
            raw_body=GOLDEN_BODY,
            signature_header=f"t={GOLDEN_TIMESTAMP},v1={'a' * 100_000}",
            secret=GOLDEN_SECRET,
            now_seconds=NOW,
        )


# ---------------------------------------------------------------------------
# The replay window
# ---------------------------------------------------------------------------


# mutation-checked 2026-09-24: replaced `abs(now - timestamp)` with
# `now - timestamp` -> 1 red, and it is the FUTURE-dated case that goes red,
# which is the whole point of the row.
class TestReplayWindow:
    def test_accepts_inside_the_window(self):
        assert (
            verify_webhook(
                GOLDEN_BODY,
                GOLDEN_HEADER,
                GOLDEN_SECRET,
                now_seconds=NOW + DEFAULT_TOLERANCE_SECONDS - 1,
            ).event
            == "member.status"
        )

    def test_refuses_a_stale_delivery(self):
        expect_rejection(
            "timestamp_out_of_tolerance",
            raw_body=GOLDEN_BODY,
            signature_header=GOLDEN_HEADER,
            secret=GOLDEN_SECRET,
            now_seconds=NOW + DEFAULT_TOLERANCE_SECONDS + 1,
        )

    def test_refuses_a_future_dated_delivery(self):
        # The half a one-sided check misses: a forged future timestamp would
        # otherwise stay valid indefinitely.
        expect_rejection(
            "timestamp_out_of_tolerance",
            raw_body=GOLDEN_BODY,
            signature_header=GOLDEN_HEADER,
            secret=GOLDEN_SECRET,
            now_seconds=NOW - DEFAULT_TOLERANCE_SECONDS - 1,
        )

    def test_accepts_exactly_at_the_boundary_both_ways(self):
        # The cheapest parity anchor available: the JS suite asserts this same
        # second, so a `>` / `>=` drift in either repo is caught.
        for now in (NOW + DEFAULT_TOLERANCE_SECONDS, NOW - DEFAULT_TOLERANCE_SECONDS):
            assert (
                verify_webhook(
                    GOLDEN_BODY, GOLDEN_HEADER, GOLDEN_SECRET, now_seconds=now
                ).event
                == "member.status"
            )

    # mutation-checked 2026-09-24: replaced the NaN/negative guard with `if
    # False` -> 1 red, exactly this row. Without it a NaN tolerance makes every
    # comparison false and the replay window silently stops existing.
    def test_refuses_a_nan_or_negative_window_rather_than_ignoring_it(self):
        for kwargs in (
            {"tolerance_seconds": float("nan")},
            {"tolerance_seconds": -1},
            {"now_seconds": float("nan")},
        ):
            expect_rejection(
                "invalid_option",
                raw_body=GOLDEN_BODY,
                signature_header=GOLDEN_HEADER,
                secret=GOLDEN_SECRET,
                **kwargs,
            )


# ---------------------------------------------------------------------------
# Secret rotation
# ---------------------------------------------------------------------------


# mutation-checked 2026-09-24: made the secrets loop `break` on the first
# candidate -> 1 red, the rotation case.
class TestSecretRotation:
    def test_accepts_a_delivery_signed_with_the_old_secret(self):
        # The real scenario: a partner rotates in the dev portal, and deliveries
        # already queued keep arriving signed with the old secret for hours.
        assert (
            verify_webhook(
                GOLDEN_BODY,
                GOLDEN_HEADER,
                ["whsec_the_brand_new_one", GOLDEN_SECRET],
                now_seconds=NOW,
            ).event
            == "member.status"
        )

    def test_still_refuses_when_none_match(self):
        expect_rejection(
            "signature_mismatch",
            raw_body=GOLDEN_BODY,
            signature_header=GOLDEN_HEADER,
            secret=["nope", "also-nope"],
            now_seconds=NOW,
        )

    @pytest.mark.parametrize("secret", [None, "", "   ", [], [None, None], [" "]])
    def test_reports_an_unusable_secret_as_its_own_reason(self, secret):
        # An unset environment variable is a misconfiguration, not an attack.
        # A whitespace-only secret counts: it passes a bare length check.
        expect_rejection(
            "no_secret_configured",
            raw_body=GOLDEN_BODY,
            signature_header=GOLDEN_HEADER,
            secret=secret,
            now_seconds=NOW,
        )


# ---------------------------------------------------------------------------
# Forward compatibility
# ---------------------------------------------------------------------------


class TestForwardCompatibility:
    def test_verifies_an_event_type_this_sdk_does_not_model(self):
        import json

        body = json.dumps(
            {
                "event": "something.invented.later",
                "eventId": "evt_future",
                "timestamp": "2026-09-24T12:00:00.000Z",
                "data": {"anything": ["at", "all"]},
            }
        )
        event = verify_webhook(
            body, sign(body, GOLDEN_SECRET, NOW), GOLDEN_SECRET, now_seconds=NOW
        )
        assert event.event == "something.invented.later"
        assert event.data == {"anything": ["at", "all"]}

    def test_accepts_an_unfamiliar_value_inside_a_known_event(self):
        import json

        # Not hypothetical: connection.revoked carried only "player_deleted"
        # until the OAuth work added "player_disconnected". A closed set here
        # would have broken every partner the day that merged. pydantic's
        # discriminated-union idiom fails closed the same way, which is why the
        # dispatch is hand-rolled.
        body = json.dumps(
            {
                "event": "connection.revoked",
                "eventId": "evt_revoked",
                "timestamp": "2026-09-24T12:00:00.000Z",
                "data": {
                    "memberId": 7204743,
                    "reason": "player_disconnected",
                    "revokedAt": "2026-09-24T12:00:00.000Z",
                },
            }
        )
        event = verify_webhook(
            body, sign(body, GOLDEN_SECRET, NOW), GOLDEN_SECRET, now_seconds=NOW
        )
        assert is_connection_revoked_event(event)
        assert event.data.reason == "player_disconnected"

    def test_accepts_an_unfamiliar_vair_pro_status(self):
        body = GOLDEN_BODY.replace(
            '"vairProStatus":null', '"vairProStatus":"SUSPENDED"'
        )
        event = verify_webhook(
            body, sign(body, GOLDEN_SECRET, NOW), GOLDEN_SECRET, now_seconds=NOW
        )
        assert is_member_status_event(event)
        assert event.data.vair_pro_status == "SUSPENDED"


# ---------------------------------------------------------------------------
# A signed but malformed event raises -- as OUR error, not pydantic's
# ---------------------------------------------------------------------------


# mutation-checked 2026-09-24: made the `except ValidationError` clause
# unreachable so pydantic's own error escaped -> 4 red (the three below plus the
# missing-sequence row in the four-event-types class). They fail on the exception
# TYPE, which is exactly the parity defect the re-raise exists to prevent: the JS
# SDK raises WebhookSignatureError and pydantic would have raised something else
# entirely, with no `reason` attribute.
class TestMalformedEvent:
    def test_raises_our_error_when_an_entitlement_field_is_missing(self):
        # Defaulting `isVairPlus` to False would deny entry to a member who
        # paid, silently, with nothing to trace. A loud failure is recoverable.
        body = GOLDEN_BODY.replace('"isVairPlus":true,', "")
        err = expect_rejection(
            "malformed_body",
            raw_body=body,
            signature_header=sign(body, GOLDEN_SECRET, NOW),
            secret=GOLDEN_SECRET,
            now_seconds=NOW,
        )
        assert "isVairPlus" in str(err) or "is_vair_plus" in str(err)

    def test_raises_when_a_field_is_the_wrong_type(self):
        body = GOLDEN_BODY.replace('"memberId":7204743', '"memberId":"not-a-number"')
        expect_rejection(
            "malformed_body",
            raw_body=body,
            signature_header=sign(body, GOLDEN_SECRET, NOW),
            secret=GOLDEN_SECRET,
            now_seconds=NOW,
        )

    def test_raises_on_a_body_that_is_not_json(self):
        body = "not json"
        expect_rejection(
            "malformed_body",
            raw_body=body,
            signature_header=sign(body, GOLDEN_SECRET, NOW),
            secret=GOLDEN_SECRET,
            now_seconds=NOW,
        )

    def test_the_error_is_never_pydantics_own(self):
        # The single highest-risk parity item: pydantic raises ValidationError
        # by default -- a different class, with no `reason`. Letting it escape
        # would mean the two SDKs fail differently on identical input.
        from pydantic import ValidationError

        body = GOLDEN_BODY.replace('"isVairPlus":true,', "")
        with pytest.raises(WebhookSignatureError) as exc:
            verify_webhook(
                body, sign(body, GOLDEN_SECRET, NOW), GOLDEN_SECRET, now_seconds=NOW
            )
        assert not isinstance(exc.value, ValidationError)
        assert exc.value.reason == "malformed_body"


# ---------------------------------------------------------------------------
# All four event types
# ---------------------------------------------------------------------------


class TestAllFourEventTypes:
    def test_rating_updated_is_the_snapshot_the_backend_actually_sends(self):
        import json

        # Built from the dispatcher, not from the polling model. Asserting
        # `newRating` here would validate a shape the emitter has not sent
        # since Vairified#899.
        body = json.dumps(
            {
                "event": "rating.updated",
                "eventId": "evt_rating",
                "timestamp": "2026-09-24T12:00:00.000Z",
                "data": {
                    "memberId": 7204743,
                    "sports": {
                        "pickleball": {
                            "rating": 3.58236,
                            "abbr": "VO",
                            "ratingSplits": {},
                            "isVairPro": False,
                        }
                    },
                    "changedAt": "2026-09-24T12:00:00.000Z",
                    "sequence": "40217",
                },
            }
        )
        event = verify_webhook(
            body, sign(body, GOLDEN_SECRET, NOW), GOLDEN_SECRET, now_seconds=NOW
        )
        assert is_rating_updated_event(event)
        assert event.data.sports["pickleball"].rating == 3.58236
        # Emitted on EVERY delivery, unlike member.status.
        assert event.data.sequence == "40217"
        assert event.data.rating_data_withheld is None

    def test_the_notification_variant_withholds_the_ratings(self):
        import json

        body = json.dumps(
            {
                "event": "rating.updated",
                "eventId": "evt_rating_withheld",
                "timestamp": "2026-09-24T12:00:00.000Z",
                "data": {
                    "memberId": 7204743,
                    "changedAt": "2026-09-24T12:00:00.000Z",
                    "sequence": "40218",
                    "ratingDataWithheld": True,
                },
            }
        )
        event = verify_webhook(
            body, sign(body, GOLDEN_SECRET, NOW), GOLDEN_SECRET, now_seconds=NOW
        )
        assert is_rating_updated_event(event)
        assert event.data.rating_data_withheld is True
        assert event.data.sports is None
        assert event.data.sequence == "40218"

    def test_raises_when_rating_updated_lacks_its_ordering_token(self):
        import json

        body = json.dumps(
            {
                "event": "rating.updated",
                "eventId": "evt_no_seq",
                "timestamp": "2026-09-24T12:00:00.000Z",
                "data": {"memberId": 7204743, "changedAt": "2026-09-24T12:00:00.000Z"},
            }
        )
        err = expect_rejection(
            "malformed_body",
            raw_body=body,
            signature_header=sign(body, GOLDEN_SECRET, NOW),
            secret=GOLDEN_SECRET,
            now_seconds=NOW,
        )
        assert "sequence" in str(err)

    def test_event_created_numeric_id_is_not_the_envelope_id(self):
        import json

        body = json.dumps(
            {
                "event": "event.created",
                "eventId": "evt_envelope",
                "timestamp": "2026-09-24T12:00:00.000Z",
                "data": {
                    "eventId": 55123,
                    "name": "Weekly League",
                    "type": "LEAGUE",
                    "status": "PUBLISHED",
                    "sport": "pickleball",
                    "startDate": None,
                    "endDate": None,
                    "club": None,
                    "hostName": None,
                    "winScore": 11,
                    "winBy": 2,
                    "isPrivate": False,
                    "maxSpots": None,
                    "maxTeams": None,
                    "createdBy": None,
                    "createdAt": "2026-09-24T12:00:00.000Z",
                },
            }
        )
        event = verify_webhook(
            body, sign(body, GOLDEN_SECRET, NOW), GOLDEN_SECRET, now_seconds=NOW
        )
        assert is_event_created_event(event)
        # The shadowing pair: envelope id is the DELIVERY, data id is the EVENT.
        assert event.event_id == "evt_envelope"
        assert event.data.event_id == 55123


# ---------------------------------------------------------------------------
# Source-enforced. NOT mutation-checkable, and deliberately NOT marked as such:
# swapping compare_digest for == returns the same value for every input, so no
# behavioural test can go red on it.
# ---------------------------------------------------------------------------


class TestSourceDiscipline:
    def test_the_comparison_is_constant_time(self):
        from pathlib import Path

        source = (Path(__file__).parent.parent / "vairified" / "webhooks.py").read_text(
            encoding="utf-8"
        )
        assert "hmac.compare_digest" in source
        # A plain `==` on a digest short-circuits on the first differing byte.
        assert "expected == signature_bytes" not in source
        assert "signature_bytes ==" not in source

    def test_models_are_frozen(self):
        event = verify_webhook(
            GOLDEN_BODY, GOLDEN_HEADER, GOLDEN_SECRET, now_seconds=NOW
        )
        assert is_member_status_event(event)
        with pytest.raises(Exception):
            event.data.is_vair_plus = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Divergences CP-2 found by running inputs neither suite covered.
# Every row here is a case where the two SDKs disagreed before the fix.
# ---------------------------------------------------------------------------


class TestCrossSdkDivergences:
    def test_a_populated_sports_block_on_member_status(self):
        # The shape 100% of production traffic has -- all four subscribing
        # connections hold rating:read -- and it had no Python test at all.
        body = GOLDEN_BODY.replace(
            '"vairProStatus":null',
            '"sports":{"pickleball":{"isVairPro":true,"isRater":true,'
            '"isVairProStatus":"ACTIVE"}},"vairProStatus":"ACTIVE"',
        )
        event = verify_webhook(
            body, sign(body, GOLDEN_SECRET, NOW), GOLDEN_SECRET, now_seconds=NOW
        )
        assert is_member_status_event(event)
        assert event.data.sports["pickleball"].is_vair_pro is True
        assert "padel" not in event.data.sports

    # mutation-checked 2026-09-24: restored `dict[str, SportRating]` on
    # RatingUpdatedEventData -> 1 red, exactly this row. That import is what made
    # Python refuse a status value JS accepts.
    def test_an_unfamiliar_per_sport_status_is_accepted(self):
        import json

        # The known gap the state matrix already names: expired and revoked
        # certifications are reported as "sport absent" today, and closing that
        # adds a status value. A closed Literal here turned that into 400s on the
        # highest-traffic event, retried ~13 times and then dropped -- for Python
        # partners only, so it would have looked like one customer's bug.
        body = json.dumps(
            {
                "event": "rating.updated",
                "eventId": "e",
                "timestamp": "t",
                "data": {
                    "memberId": 1,
                    "changedAt": "c",
                    "sequence": "1",
                    "sports": {
                        "pickleball": {
                            "rating": 4.2,
                            "abbr": "VO",
                            "ratingSplits": {},
                            "isVairProStatus": "SUSPENDED",
                        }
                    },
                },
            }
        )
        event = verify_webhook(
            body, sign(body, GOLDEN_SECRET, NOW), GOLDEN_SECRET, now_seconds=NOW
        )
        assert is_rating_updated_event(event)
        assert event.data.sports["pickleball"].is_vair_pro_status == "SUSPENDED"

    # mutation-checked 2026-09-24: dropped `value.isascii()` from the timestamp
    # guard -> 1 red, and it fails with a raw ValueError rather than ours, which
    # is the whole finding.
    @pytest.mark.parametrize("digit", ["\u00b2", "\u0663"])
    def test_a_unicode_digit_in_t_is_our_error_not_a_raw_valueerror(self, digit):
        # `str.isdigit()` is True for superscripts and Arabic-Indic digits that
        # `int()` then refuses. Anyone who knows the URL can send one; no secret
        # needed. The documented handler catches only our error, so a raw
        # ValueError 500s the receiver.
        expect_rejection(
            "malformed_signature",
            raw_body=GOLDEN_BODY,
            signature_header=f"t={digit},v1=aa",
            secret=GOLDEN_SECRET,
            now_seconds=NOW,
        )

    # mutation-checked 2026-09-24: replaced `math.isfinite(...)` with a bare
    # NaN check -> 1 red, and a 31-year-stale delivery verifies again.
    def test_an_infinite_window_is_refused_not_obeyed(self):
        # `float("inf")` parses from an env var where JS's `Number("inf")` is
        # NaN and already refused. Accepting it disables the only replay control
        # the verifier applies -- and fails open, so nothing warns.
        expect_rejection(
            "invalid_option",
            raw_body=GOLDEN_BODY,
            signature_header=GOLDEN_HEADER,
            secret=GOLDEN_SECRET,
            now_seconds=NOW,
            tolerance_seconds=float("inf"),
        )

    # mutation-checked 2026-09-24: removed `strict=True` from _EVENT_CONFIG ->
    # 3 red, each on a field pydantic silently coerced.
    @pytest.mark.parametrize(
        "old,new",
        [
            ('"memberId":7204743', '"memberId":"7204743"'),
            ('"isVairPlus":true', '"isVairPlus":"true"'),
            ('"memberId":7204743', '"member_id":7204743'),
        ],
    )
    def test_entitlement_fields_are_not_coerced(self, old, new):
        # Lax pydantic turns "42" into 42 and "false" into False -- inventing a
        # value for the field that gates paid entry, on input JS refuses.
        body = GOLDEN_BODY.replace(old, new)
        expect_rejection(
            "malformed_body",
            raw_body=body,
            signature_header=sign(body, GOLDEN_SECRET, NOW),
            secret=GOLDEN_SECRET,
            now_seconds=NOW,
        )

    def test_an_empty_v1_is_malformed_not_a_mismatch(self):
        # `bytes.fromhex("")` returns b"" rather than raising, so this reported
        # "someone is forging requests" for what is a broken header.
        expect_rejection(
            "malformed_signature",
            raw_body=GOLDEN_BODY,
            signature_header=f"t={GOLDEN_TIMESTAMP},v1=",
            secret=GOLDEN_SECRET,
            now_seconds=NOW,
        )

    def test_an_envelope_failure_reads_like_the_typescript_one(self):
        body = '{"hello":"world"}'
        err = expect_rejection(
            "malformed_body",
            raw_body=body,
            signature_header=sign(body, GOLDEN_SECRET, NOW),
            secret=GOLDEN_SECRET,
            now_seconds=NOW,
        )
        assert "missing a string" in str(err)
        assert "'None'" not in str(err)
