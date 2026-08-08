"""Dashboard slot reuse — guards against rows showing another account's data."""
import time

from dashboard import FarmDashboard


def test_slot_reuse_clears_previous_account():
    d = FarmDashboard(total=6, max_workers=3)

    d.update_worker(0, status="registering", email="a@x.id", error="", started_at=time.monotonic())
    d.finish_worker(0, success=False, error="No OTP for a@x.id")
    assert d._workers[0].email == "a@x.id"
    assert d._workers[0].error == "No OTP for a@x.id"

    d.update_worker(0, status="registering", email="c@x.id", error="", started_at=time.monotonic())
    assert d._workers[0].email == "c@x.id", "email must follow the current account"
    assert d._workers[0].error == "", "stale error must not leak into the next account"
    assert d._workers[0].done is False, "reused slot must not stay marked done"


def test_counters_advance_on_finish():
    d = FarmDashboard(total=3, max_workers=2)
    d.update_worker(0, status="registering", email="a@x.id", started_at=time.monotonic())
    d.update_worker(1, status="registering", email="b@x.id", started_at=time.monotonic())

    d.finish_worker(0, success=True)
    d.finish_worker(1, success=False, error="boom")

    assert (d._success, d._failed) == (1, 1)
    header = d._header().plain
    assert "Success: 1" in header and "Failed: 1" in header


def test_elapsed_renders_once_started():
    d = FarmDashboard(total=1, max_workers=1)
    assert d._workers[0].elapsed == "-"
    d.update_worker(0, status="registering", email="a@x.id", started_at=time.monotonic() - 5)
    assert d._workers[0].elapsed.endswith("s") and d._workers[0].elapsed != "-"


if __name__ == "__main__":
    test_slot_reuse_clears_previous_account()
    test_counters_advance_on_finish()
    test_elapsed_renders_once_started()
    print("all dashboard tests passed")
