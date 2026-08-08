"""Application configuration for the Blackbox farm."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(slots=True)
class Config:
    """Static run configuration. Override via CLI flags when needed."""

    blackbox_url: str = "https://app.blackbox.ai"
    tempmail_domain: str = ""
    tempmail_provider: str = "cloudflare"
    cloudflare_api_url: str = os.getenv("CF_API_URL", "https://your-worker.workers.dev")
    cloudflare_default_domain: str = os.getenv("CF_DEFAULT_DOMAIN", "example.com")
    proxy_file: str = os.getenv("PROXY_FILE", "proxies.txt")
    max_workers: int = 3
    verify_poll_timeout: int = 60
    verify_poll_interval: int = 3
    otp_resend_attempts: int = 3
    request_timeout: int = 120
    output_dir: str = "output"
    # Extra knobs kept off the main path but useful for debugging.
    headless: bool = True
    random_delay_min: float = 3.0
    random_delay_max: float = 10.0
    cooldown_min: float = 10.0
    cooldown_max: float = 20.0
    key_name: str = "gaco-dev"

    @property
    def delay_range(self) -> tuple[float, float]:
        return (self.random_delay_min, self.random_delay_max)

    @property
    def cooldown_range(self) -> tuple[float, float]:
        return (self.cooldown_min, self.cooldown_max)

    def with_updates(self, **updates: object) -> "Config":
        """Return a copy with the given dataclass fields replaced."""
        merged = {f.name: getattr(self, f.name) for f in field(self)}
        merged.update(updates)
        return Config(**merged)  # type: ignore[arg-type]
