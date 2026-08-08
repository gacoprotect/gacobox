"""Application configuration for the Blackbox farm."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(slots=True)
class Config:
    """Static run configuration. Override via CLI flags when needed."""

    blackbox_url: str = "https://app.blackbox.ai"
    tempmail_domain: str = os.getenv("TEMPMAIL_DOMAIN", "")
    tempmail_provider: str = os.getenv("TEMPMAIL_PROVIDER", "cloudflare")
    cloudflare_api_url: str = os.getenv("CF_API_URL", "https://your-worker.workers.dev")
    cloudflare_default_domain: str = os.getenv("CF_DEFAULT_DOMAIN", "example.com")
    proxy_file: str = os.getenv("PROXY_FILE", "proxies.txt")
    warp_cli: str = os.getenv("WARP_CLI", "warp-cli")
    warp_rotate: bool = os.getenv("WARP_ROTATE", "0") not in ("0", "false", "")
    warp_cycle: int = int(os.getenv("WARP_CYCLE", "1"))
    max_workers: int = int(os.getenv("WORKERS", "5"))
    count: int = int(os.getenv("COUNT", "20"))
    use_proxy: bool = os.getenv("USE_PROXY", "0") not in ("0", "false", "")
    verify_poll_timeout: int = int(os.getenv("VERIFY_POLL_TIMEOUT", "60"))
    verify_poll_interval: int = int(os.getenv("VERIFY_POLL_INTERVAL", "5"))
    otp_resend_attempts: int = int(os.getenv("OTP_RESEND_ATTEMPTS", "3"))
    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "120"))
    output_dir: str = "output"
    debug: bool = os.getenv("DEBUG", "1") not in ("0", "false", "")
    # Extra knobs kept off the main path but useful for debugging.
    headless: bool = os.getenv("HEADLESS", "1") not in ("0", "false", "")
    random_delay_min: float = float(os.getenv("DELAY_MIN", "3.0"))
    random_delay_max: float = float(os.getenv("DELAY_MAX", "10.0"))
    cooldown_min: float = float(os.getenv("COOLDOWN_MIN", "10.0"))
    cooldown_max: float = float(os.getenv("COOLDOWN_MAX", "20.0"))
    warp_stagger_min: float = float(os.getenv("WARP_STAGGER_MIN", "1.0"))
    warp_stagger_max: float = float(os.getenv("WARP_STAGGER_MAX", "5.0"))
    key_name: str = "gaco-dev"

    @property
    def delay_range(self) -> tuple[float, float]:
        return (self.random_delay_min, self.random_delay_max)

    @property
    def cooldown_range(self) -> tuple[float, float]:
        return (self.cooldown_min, self.cooldown_max)

    @property
    def warp_stagger_range(self) -> tuple[float, float]:
        return (self.warp_stagger_min, self.warp_stagger_max)

    def with_updates(self, **updates: object) -> "Config":
        """Return a copy with the given dataclass fields replaced."""
        merged = {f.name: getattr(self, f.name) for f in field(self)}
        merged.update(updates)
        return Config(**merged)  # type: ignore[arg-type]
