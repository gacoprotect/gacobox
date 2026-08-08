"""Bench domains that stop delivering OTP mail.

Some mailbox domains get silently dropped by Blackbox: signup succeeds, resend
succeeds, no mail ever lands. Retrying them burns a full resend cycle per
account, so a domain that fails every round is parked and skipped on later
runs. State lives in a JSON file because runs are separate processes.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

_STATE_FILE = Path(__file__).resolve().parent.parent / "output" / "domain_cooldown.json"
COOLDOWN_SECONDS = 3600.0


def _load() -> dict[str, float]:
    try:
        raw = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, (int, float))}


def _save(state: dict[str, float]) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(_STATE_FILE)


def penalize(domain: str, seconds: float = COOLDOWN_SECONDS) -> float:
    state = _load()
    state[domain] = time.time() + seconds
    _save(state)
    return seconds


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
