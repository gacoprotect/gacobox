"""WARP rotation barrier — guards against rotating while a signup is in flight."""
import asyncio

from providers import warp


def _run(count, workers, cycle, fail_every=0):
    """Drive `count` accounts through the barrier, reporting rotations and overlap."""
    rotations = []
    inflight = 0
    max_inflight_during_rotation = 0

    async def fake_rotate(warp_cli="warp-cli"):
        nonlocal max_inflight_during_rotation
        max_inflight_during_rotation = max(max_inflight_during_rotation, inflight)
        rotations.append(1)
        await asyncio.sleep(0.02)
        return True

    async def scenario():
        nonlocal inflight
        barrier = warp.RotationBarrier(cycle, workers)
        lock = asyncio.Lock()
        held = set()
        finished = 0

        async def account(i):
            nonlocal inflight, finished
            wid = await barrier.enter()
            assert wid not in held, f"slot {wid} handed to two accounts at once"
            held.add(wid)
            inflight += 1
            try:
                await asyncio.sleep(0.01)
                if fail_every and i % fail_every == 0:
                    raise RuntimeError("signup failed")
            except RuntimeError:
                pass
            finally:
                inflight -= 1
                held.discard(wid)
                async with lock:
                    finished += 1
                    remaining = count - finished
                await barrier.account_done(remaining=remaining, worker_id=wid)

        await asyncio.wait_for(
            asyncio.gather(*[account(i) for i in range(count)]), timeout=30
        )
        return barrier.every

    original = warp.rotate
    warp.rotate = fake_rotate
    try:
        every = asyncio.run(scenario())
    finally:
        warp.rotate = original
    return every, len(rotations), max_inflight_during_rotation


def test_rotation_never_overlaps_a_signup():
    for count, workers, cycle in [(20, 3, 2), (100, 3, 2), (13, 3, 2), (10, 1, 2)]:
        _, _, overlap = _run(count, workers, cycle)
        assert overlap == 0, f"rotated while {overlap} signups were in flight ({count=}, {workers=})"


def _rotation_gaps(count, workers, cycle, durations):
    """Return how many accounts finished between rotations, with uneven signups.

    Equal-length signups drain instantly, which hides drift caused by the
    accounts that were still in flight when the gate closed.
    """
    gaps = []
    completed = 0
    last = 0

    async def fake_rotate(warp_cli="warp-cli"):
        gaps.append(completed - last)
        await asyncio.sleep(0.01)
        return warp.Rotation(ip="1.2.3.4", moved=True)

    async def scenario():
        nonlocal completed, last
        barrier = warp.RotationBarrier(cycle, workers)
        lock = asyncio.Lock()
        finished = 0

        async def account(i):
            nonlocal completed, finished, last
            wid = await barrier.enter()
            await asyncio.sleep(durations[i % len(durations)])
            async with lock:
                finished += 1
                completed += 1
                remaining = count - finished
            before = len(gaps)
            await barrier.account_done(remaining=remaining, worker_id=wid)
            if len(gaps) > before:
                last = completed

        await asyncio.wait_for(
            asyncio.gather(*[account(i) for i in range(count)]), timeout=30
        )

    original = warp.rotate
    warp.rotate = fake_rotate
    try:
        asyncio.run(scenario())
    finally:
        warp.rotate = original
    return gaps


def test_rotation_spacing_does_not_drift():
    # The drain lets `workers - 1` accounts finish after the gate closes; they
    # must not count against the next cycle, or every later rotation lands early.
    gaps = _rotation_gaps(20, 4, 2, durations=[0.01, 0.05, 0.09, 0.13])
    assert len(gaps) >= 2, f"expected repeated rotations, got {gaps}"
    for gap in gaps[1:]:
        assert gap == 8, f"cycles after the first must stay 8 accounts apart, got {gaps}"


def test_rotates_every_cycle_times_workers():
    for count, workers, cycle in [(20, 3, 2), (100, 3, 2), (18, 3, 2), (10, 1, 2), (30, 5, 2)]:
        every, rotations, _ = _run(count, workers, cycle)
        assert every == cycle * workers, f"{every=} should be {cycle}*{workers}"
        assert rotations == (count - 1) // every, f"{rotations=} for {count=} {every=}"


def test_trailing_group_is_released_without_rotating():
    # A run that never reaches the threshold must not rotate at all, and a run
    # that ends exactly on it must not spend a rotation nobody will use.
    for count, workers, cycle in [(5, 3, 2), (6, 3, 2), (3, 3, 1), (1, 3, 2), (20, 4, 5)]:
        _, rotations, _ = _run(count, workers, cycle)
        assert rotations == (count - 1) // (cycle * workers), f"{rotations=} for {count=}"


def test_failed_accounts_still_release_the_gate():
    for count, workers, cycle, fail_every in [(20, 3, 2, 3), (30, 5, 2, 4)]:
        every, rotations, overlap = _run(count, workers, cycle, fail_every)
        assert overlap == 0
        assert rotations == (count - 1) // every, "a failed signup must still count toward rotation"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
