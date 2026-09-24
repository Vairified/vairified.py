"""The shared conformance suite.

``conformance/webhook-cases.json`` is byte-identical in ``vairified.py`` and
``vairified.js``, and both run every case in their own CI. That is what makes
parity a build failure instead of something a person asserts.

It exists because parity WAS something a person asserted, and the assertion was
wrong twice: one pass reported 13 of 13 cases agreeing, a review then found 14
more that all diverged, and a third pass found 15 real divergences in 41 cases.
Fixing named instances was not converging, so the mechanism changed rather than
the instances.

**Adding a case:** edit the JSON in BOTH repos, byte-identical. A reviewer who
finds a divergence contributes a case here rather than a bug report -- that is
the property that makes this converge.
"""

import json
import math
from pathlib import Path

import pytest

from vairified import verify_webhook
from vairified.errors import WebhookSignatureError

_SUITE = json.loads(
    (Path(__file__).parent.parent / "conformance" / "webhook-cases.json").read_text(
        encoding="utf-8"
    )
)
_CASES = _SUITE["cases"]


def _tolerance(v):
    """JSON has no literal for these, so the file carries them as strings.

    Without this the two most dangerous option values -- the ones that silently
    disabled the replay window -- could not be expressed in a shared file at all.
    """
    if v is None:
        return None
    if v == "NaN":
        return math.nan
    if v == "Infinity":
        return math.inf
    return v


def test_suite_matches_what_the_typescript_sdk_runs():
    # A cheap guard against one repo's file being edited alone. It cannot prove
    # the two files match -- only CI fetching the sibling could -- but it pins
    # the count and version so a silent truncation is visible.
    assert _SUITE["version"] == 2
    assert len(_CASES) >= 55
    assert len({c["name"] for c in _CASES}) == len(_CASES)


def test_every_reject_case_declares_its_reason():
    """Without this, a case added with no ``reason`` would quietly fall back to a
    verdict-only check -- the exact weakness the field was added to close,
    reintroduced one case at a time."""
    for case in _CASES:
        if case["name"].startswith("reject/"):
            assert isinstance(case.get("reason"), str), case["name"]
        else:
            assert "reason" not in case, case["name"]


# mutation-checked 2026-09-24: deleted both bad-`v1` refusal paths (the
# odd-length guard and the hex-decode except) -> 3 red (reject/empty-signature,
# reject/non-hex-signature, reject/odd-length-signature), messages name the
# behaviour: "assert 'signature_mismatch' == 'malformed_signature'". The SAME
# mutant against the previous verdict-only assertion produced 0 red, which is
# what established that checking the reason was load-bearing rather than tidy.
@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_conformance(case):
    body = bytes.fromhex(case["bodyHex"])
    kwargs = {"now_seconds": case["nowSeconds"]}
    tol = _tolerance(case.get("toleranceSeconds"))
    if tol is not None:
        kwargs["tolerance_seconds"] = tol

    secret = case["secret"]
    if secret is not None and not isinstance(secret, str):
        secret = list(secret)

    if case["name"].startswith("accept/"):
        event = verify_webhook(body, case["header"], secret, **kwargs)
        assert isinstance(event.event, str), case["why"]
        assert isinstance(event.event_id, str), case["why"]
    else:
        # The REASON is asserted, not just the refusal. Checking the verdict
        # alone was measured to be too weak: with both bad-`v1` refusal paths
        # deleted, every case still passed, because a corrupted digest simply
        # failed the comparison and came back `signature_mismatch` -- still a
        # refusal. The two SDKs could therefore agree to reject and disagree
        # about why, which is the class of divergence this suite exists to end.
        # The reason is public API: `no_secret_configured` sends a partner to an
        # environment variable, `signature_mismatch` sends them looking for an
        # attacker.
        with pytest.raises(WebhookSignatureError) as excinfo:
            verify_webhook(body, case["header"], secret, **kwargs)
        assert excinfo.value.reason == case["reason"], case["why"]
