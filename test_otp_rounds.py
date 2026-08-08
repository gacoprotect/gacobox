"""`otp_resend_attempts` counts Resend clicks; each click gets its own poll."""
import asyncio
import types

from config import Config
from providers import blackbox


def _drive(clicks, otp_on_poll=None, resend_ok=True, resend_reason="503: Service Unavailable"):
    cfg = Config()
    cfg.otp_resend_attempts = clicks
    cfg.tempmail_provider = "catchmail"
    client = blackbox.BlackboxClient.__new__(blackbox.BlackboxClient)
    client._cfg = cfg
    client._proxy = None
    events = []
    seen = {"polls": 0}

    async def fake_wait(email, config):
        seen["polls"] += 1
        events.append("POLL")
        if otp_on_poll and seen["polls"] == otp_on_poll:
            return "123456"
        raise blackbox.BlackboxError("no otp")

    async def fake_resend(email):
        events.append("CLICK_OK" if resend_ok else "CLICK_REJECTED")
        return "" if resend_ok else resend_reason

    async def fake_snapshot(email, tag):
        return None

    original = blackbox.tempmail
    blackbox.tempmail = types.SimpleNamespace(wait_for_otp=fake_wait)
    client._click_resend = fake_resend
    client._snapshot = fake_snapshot
    try:
        asyncio.run(
            client._await_otp_with_resend("a@b.com", "", lambda s: events.append(s))
        )
    except Exception:
        pass
    finally:
        blackbox.tempmail = original
    return events


def test_every_accepted_click_is_followed_by_a_poll():
    for clicks in (0, 1, 2, 4):
        events = _drive(clicks)
        for i, ev in enumerate(events):
            if ev == "CLICK_OK":
                assert events[i + 1 : i + 3] == ["waiting_verify", "POLL"], (
                    f"click at {i} not followed by a wait+poll: {events}"
                )
        assert events[-1] == "POLL", f"run must end on a poll, got {events[-1]}"


def test_config_value_is_the_click_count():
    # `otp_resend_attempts=3` must mean three presses labelled 3/3, not 2/2.
    for clicks in (1, 3, 5):
        events = _drive(clicks)
        labels = [e for e in events if e.startswith("resend ")]
        assert labels == [f"resend {i}/{clicks}" for i in range(1, clicks + 1)], labels
        assert events.count("CLICK_OK") == clicks
        assert events.count("POLL") == clicks + 1, events


def test_rejected_resend_still_polls_the_remaining_rounds():
    # Production: 82 accounts died in ~50s because a rejected resend was retried
    # in place (2s, 4s) and then ended the run, so rounds 2 and 3 never polled.
    # A 500 is Blackbox's problem; the signup mail can still arrive.
    events = _drive(3, resend_ok=False)
    assert events.count("POLL") == 4, events
    assert events.count("CLICK_REJECTED") == 3, events
    assert events[-1] == "POLL", events


def test_early_otp_stops_the_rounds():
    events = _drive(3, otp_on_poll=2)
    assert events.count("POLL") == 2, events
    assert events.count("CLICK_OK") == 1, events


def test_the_real_failure_reason_reaches_the_dashboard():
    # The Error column hardcoded "HTTP 500" because _click_resend returned a
    # bool, so a 429 or a click that sent no request all read as a 500.
    for reason in ("429: Too many requests", "button disabled: Resend in 45s"):
        events = _drive(2, resend_ok=False, resend_reason=reason)
        setbacks = [e for e in events if e.startswith("!")]
        assert setbacks == [f"!{reason}", f"!2x {reason}"], setbacks


def test_error_text_quotes_the_server_not_a_hardcoded_500():
    from providers.blackbox import _server_message

    # The dashboard used to read "resend HTTP 500" for every failure. The
    # status is real, but the wording has to come from the response body:
    # two 500s with different messages are different problems.
    assert _server_message('{"error":"Failed to send verification code"}') == (
        "Failed to send verification code"
    )
    assert _server_message('{"message":"Too many requests"}') == "Too many requests"
    assert _server_message("Service Unavailable") == "Service Unavailable"
    assert _server_message("") == ""


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
