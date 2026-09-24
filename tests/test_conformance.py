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
    assert _SUITE["version"] == 1
    assert len(_CASES) >= 53
    assert len({c["name"] for c in _CASES}) == len(_CASES)


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
        with pytest.raises(WebhookSignatureError):
            verify_webhook(body, case["header"], secret, **kwargs)
