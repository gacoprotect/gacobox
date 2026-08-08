"""Domains available on the Cloudflare Workers temp mailbox.

Real domains live in domains.txt (gitignored) so a public checkout never leaks
the operator's mailbox namespace; the fallback keeps the module importable.
"""
from __future__ import annotations

import secrets
from pathlib import Path

_DOMAIN_FILE = Path(__file__).resolve().parent.parent / "domains.txt"

_FALLBACK_DOMAINS = ["example.com"]


def _load_domains() -> list[str]:
    if not _DOMAIN_FILE.exists():
        return list(_FALLBACK_DOMAINS)
    lines = [
        line.strip()
        for line in _DOMAIN_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    return lines or list(_FALLBACK_DOMAINS)


CLOUDFLARE_DOMAINS = _load_domains()


def get_random_domain() -> str:
    from providers import domain_cooldown

    usable = [d for d in CLOUDFLARE_DOMAINS if not domain_cooldown.is_cooling(d)]
    # Every domain benched at once means the fault is upstream, not per-domain;
    # falling back to the full list beats refusing to run.
    if not usable:
        return secrets.choice(CLOUDFLARE_DOMAINS)
    chosen = secrets.choice(usable)
    domain_cooldown.record_use(chosen)
    return chosen
