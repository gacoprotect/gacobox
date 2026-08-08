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
    """Rotates the WARP egress once every `cycle` accounts per worker.

    WARP moves the egress for every worker at once, so a rotation may only run
    while no signup is in flight. Rotation is counted against the run as a
    whole - `cycle=2` with 3 workers rotates every 6th finished account - and
    the worker that trips the count closes the gate, waits for the others to
    finish what they already started, rotates, then reopens it.

    Workers announce themselves with `enter()` before each account and
    `account_done()` after. Nothing rotates once `remaining` hits zero: a fresh
    egress no signup will use only costs the run a WARP reconnect.
    """

    def __init__(
        self,
        cycle: int,
        workers: int,
        warp_cli: str = "warp-cli",
        on_rotate: "Callable[[Rotation], None] | None" = None,
    ) -> None:
        self.every = max(1, cycle) * max(1, workers)
        self._warp_cli = warp_cli
        self._on_rotate = on_rotate
        self._since_rotation = 0
        self._active = 0
        self._lock = asyncio.Lock()
        self._open = asyncio.Event()
        self._open.set()
        self._drained = asyncio.Event()
        self._drained.set()

    async def enter(self) -> None:
        while True:
            await self._open.wait()
            async with self._lock:
                if self._open.is_set():
                    self._active += 1
                    self._drained.clear()
                    return

    async def account_done(self, remaining: int) -> None:
        async with self._lock:
            self._active -= 1
            if self._active == 0:
                self._drained.set()
            self._since_rotation += 1
            if self._since_rotation < self.every or remaining <= 0:
                return
            self._since_rotation = 0
            self._open.clear()

        await self._drained.wait()
        try:
            result = await rotate(self._warp_cli)
            if self._on_rotate:
                self._on_rotate(result)
        finally:
            self._open.set()
