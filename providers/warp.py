"""WARP egress rotation via warp-cli.

Used as the no-proxy alternative: when the pool is off, accounts still need
different egress IPs between signups. WARP is one system-wide tunnel, so a
rotation moves the IP for every worker at once and the calls are serialised.
That also means WARP cannot give concurrent workers distinct IPs - the proxy
pool is the only thing that can.

Best-effort throughout: a machine without warp-cli just gets no rotation.
"""
from __future__ import annotations

import asyncio
import secrets
import shutil
from dataclasses import dataclass
from typing import Callable

from logger import get_logger

_lock = asyncio.Lock()


def available(warp_cli: str = "warp-cli") -> bool:
    return shutil.which(warp_cli) is not None


async def _run(warp_cli: str, *args: str, timeout: float = 60) -> tuple[bool, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            warp_cli, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except (FileNotFoundError, OSError) as exc:
        return False, str(exc)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return False, f"{' '.join(args)} timed out after {timeout:.0f}s"
    return proc.returncode == 0, (out or b"").decode(errors="replace").strip()


async def public_ip() -> str:
    import httpx

    try:
        async with httpx.AsyncClient(trust_env=False, timeout=8) as client:
            resp = await client.get("https://api.ipify.org")
            return resp.text.strip() if resp.status_code == 200 else ""
    except httpx.HTTPError:
        return ""


@dataclass(frozen=True)
class Rotation:
    """Outcome of a rotation attempt.

    `ip` is the egress as it stands afterwards, whether or not it moved, so the
    caller can always show where traffic is going. `fatal` separates "the
    tunnel is unusable" (warp-cli missing, connect failed) from "the egress
    simply did not change", which is disappointing but still workable.
    """

    ip: str = ""
    moved: bool = False
    fatal: bool = False
    detail: str = ""

    def __bool__(self) -> bool:
        return self.moved


async def rotate(warp_cli: str = "warp-cli") -> Rotation:
    """Rotate the WARP egress by re-registering.

    Only a fresh registration moves the egress; disconnect/connect measurably
    hands back the same IP, so it is not attempted.
    """
    log = get_logger()
    if not available(warp_cli):
        log.debug("warp-cli not in PATH, skipping rotation")
        return Rotation(fatal=True, detail="warp-cli not installed")

    async with _lock:
        before = await public_ip()
        await _run(warp_cli, "disconnect")
        ok_del, _ = await _run(warp_cli, "registration", "delete")
        if not ok_del:
            await _run(warp_cli, "registration", "clear")
        ok_new, out_new = await _run(warp_cli, "registration", "new")
        if not ok_new:
            log.warning("warp registration new failed: %s", out_new[:120])
            # Reconnecting on the old registration keeps the run online even
            # though the egress never moved.
            await _run(warp_cli, "connect")
            return Rotation(ip=await public_ip(), detail="registration failed")

        ok_conn, out_conn = await _run(warp_cli, "connect")
        if not ok_conn:
            log.warning("warp connect failed: %s", out_conn[:120])
            return Rotation(fatal=True, detail="connect failed")
        # Routes settle a moment after connect returns; checking immediately
        # still reports the previous egress.
        await asyncio.sleep(3)

        after = await public_ip()
        if after and before and after != before:
            log.info("warp rotated: %s -> %s", before, after)
            return Rotation(ip=after, moved=True)
        if not after:
            log.warning("warp connected but the egress IP is unknown")
            return Rotation(fatal=True, detail="no egress IP")
        log.warning("warp IP still %s after re-register", after)
        return Rotation(ip=after, detail="IP unchanged")


class RotationBarrier:
    """Rotates the WARP egress once every worker has used up `cycle` accounts.

    WARP moves the egress for every worker at once, so a rotation may only run
    while no signup is in flight. This also hands out the worker slots, because
    admission and rotation are the same decision: a slot is a unit of quota, and
    handing one back to a spent worker would let the next account borrow quota
    that is already used up. `enter()` returns the slot to run on and blocks
    until one is free and the gate is open; `account_done()` returns it. Exactly
    `cycle * workers` accounts share an IP.

    Counting per worker rather than against a running total is what keeps the
    spacing honest - a global counter trips while other workers are mid-signup,
    and those accounts land on the next IP, pulling every later rotation early.

    Nothing rotates once `remaining` hits zero: a fresh egress no signup will
    use only costs the run a WARP reconnect.
    """

    def __init__(
        self,
        cycle: int,
        workers: int,
        warp_cli: str = "warp-cli",
        on_rotate: "Callable[[Rotation], None] | None" = None,
        on_wait: "Callable[[int, str], None] | None" = None,
        stagger: "tuple[float, float] | None" = None,
    ) -> None:
        self._cycle = max(1, cycle)
        self._workers = max(1, workers)
        self.every = self._cycle * self._workers
        self._warp_cli = warp_cli
        self._on_rotate = on_rotate
        self._on_wait = on_wait
        self._used: dict[int, int] = {}
        self._parked = 0
        self._live = 0
        self._queued = 0
        self._free = list(range(self._workers))
        self._lock = asyncio.Lock()
        self._resume = asyncio.Event()
        self._resume.set()
        self._slot_free = asyncio.Event()
        self._slot_free.set()
        self._stagger = stagger

    async def enter(self) -> int:
        waited = False
        async with self._lock:
            self._queued += 1
        try:
            while True:
                async with self._lock:
                    if self._resume.is_set() and self._free:
                        wid = self._free.pop(0)
                        self._live += 1
                        self._queued -= 1
                        break
                    gate = self._resume.wait()
                    slot = self._slot_free.wait()
                    self._slot_free.clear()
                waited = True
                done, pending = await asyncio.wait(
                    [asyncio.ensure_future(gate), asyncio.ensure_future(slot)],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
        except BaseException:
            async with self._lock:
                self._queued -= 1
            raise

        # Only a worker that actually queued gets staggered. A rotation frees
        # every slot at once, so without this they all reach signup on the same
        # second behind the fresh egress and look like one burst of traffic.
        if waited and self._stagger:
            await asyncio.sleep(secrets.SystemRandom().uniform(*self._stagger))
        if waited and self._on_wait:
            self._on_wait(wid, "")
        return wid

    async def account_done(self, remaining: int, worker_id: int) -> None:
        async with self._lock:
            self._live -= 1
            self._used[worker_id] = self._used.get(worker_id, 0) + 1
            parked = self._used[worker_id] >= self._cycle and remaining > 0
            if parked:
                self._parked += 1
            else:
                self._free.append(worker_id)

            # Admission lives here rather than behind a separate semaphore so
            # that a spent worker can keep its slot out of circulation. Handing
            # the slot straight back lets the next account run on the same
            # worker's exhausted quota, which is what stretched a cycle to the
            # whole run. The egress moves once every slot is either parked or
            # has no account left to claim it.
            rotate_now = self._parked > 0 and self._live == 0 and remaining > 0 and (
                self._parked >= self._workers or self._queued == 0 or not self._free
            )
            if not rotate_now:
                self._slot_free.set()
                return
            self._resume.clear()

        await self._rotate_and_release(worker_id)

    async def _rotate_and_release(self, worker_id: int) -> None:
        try:
            if self._on_wait:
                self._on_wait(worker_id, "rotating WARP")
            result = await rotate(self._warp_cli)
            if self._on_rotate:
                self._on_rotate(result)
        finally:
            async with self._lock:
                self._used.clear()
                self._parked = 0
                self._free = list(range(self._workers))
            self._resume.set()
            self._slot_free.set()
            if self._on_wait:
                self._on_wait(worker_id, "")
