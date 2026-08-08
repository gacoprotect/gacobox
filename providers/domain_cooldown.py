"""Bench domains that stop delivering OTP mail, and rotate the healthy ones.

Some mailbox domains get silently dropped by Blackbox: signup succeeds, resend
succeeds, no mail ever lands. Retrying them burns a full resend cycle per
account, so a domain that fails every round is parked and skipped on later
runs. Healthy domains are also rested after a few signups so no single domain
carries the whole run and draws a flag. State lives in a JSON file because runs
are separate processes.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

_STATE_FILE = Path(__file__).resolve().parent.parent / "output" / "domain_cooldown.json"
COOLDOWN_SECONDS = 3600.0
USES_BEFORE_REST = 3
REST_SECONDS = 900.0


def _read() -> dict:
    try:
        raw = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _load() -> dict[str, float]:
    raw = _read()
    # Pre-rotation files were a flat {domain: expiry} map; treat them as such so
    # an upgrade mid-cooldown does not un-bench a domain that is still bad.
    cools = raw.get("cooldowns", raw) if "uses" in raw or "cooldowns" in raw else raw
    if not isinstance(cools, dict):
        return {}
    return {k: v for k, v in cools.items() if isinstance(k, str) and isinstance(v, (int, float))}


def _load_uses() -> dict[str, int]:
    raw = _read().get("uses")
    if not isinstance(raw, dict):
        return {}
    return {k: int(v) for k, v in raw.items() if isinstance(k, str) and isinstance(v, (int, float))}


def _save(state: dict[str, float], uses: dict[str, int] | None = None) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"cooldowns": state, "uses": _load_uses() if uses is None else uses}
    tmp = _STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(_STATE_FILE)


def penalize(domain: str, seconds: float = COOLDOWN_SECONDS) -> float:
    state = _load()
    state[domain] = time.time() + seconds
    uses = _load_uses()
    uses.pop(domain, None)
    _save(state, uses)
    return seconds


def record_use(domain: str) -> float:
    uses = _load_uses()
    count = uses.get(domain, 0) + 1
    if count < USES_BEFORE_REST:
        uses[domain] = count
        _save(_load(), uses)
        return 0.0
    uses.pop(domain, None)
    state = _load()
    state[domain] = time.time() + REST_SECONDS
    _save(state, uses)
    return REST_SECONDS


def is_cooling(domain: str) -> bool:
    return remaining(domain) > 0


def remaining(domain: str) -> float:
    expiry = _load().get(domain)
    if expiry is None:
        return 0.0
    return max(0.0, expiry - time.time())


def active() -> dict[str, float]:
    now = time.time()
    return {d: e - now for d, e in _load().items() if e > now}
