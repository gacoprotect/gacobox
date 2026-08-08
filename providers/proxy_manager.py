"""Proxy manager for rotating proxies."""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Optional


class ProxyManager:
    """Load and rotate proxies from file."""

    def __init__(self, proxy_file: str):
        self.proxy_file = Path(proxy_file)
        self.proxies: list[str] = []
        self._load_proxies()

    def _load_proxies(self) -> None:
        """Load proxies from file, skip comments and empty lines."""
        if not self.proxy_file.exists():
            return

        try:
            content = self.proxy_file.read_text(encoding="utf-8")
            self.proxies = [
                line.strip()
                for line in content.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
        except Exception as e:
            print(f"Warning: Failed to load proxies: {e}")
            self.proxies = []

    def get_random_proxy(self) -> Optional[str]:
        """Get a random proxy from the list, or None if no proxies available."""
        if not self.proxies:
            return None
        return secrets.choice(self.proxies)

    def has_proxies(self) -> bool:
        """Check if any proxies are available."""
        return len(self.proxies) > 0

    def count(self) -> int:
        """Return number of available proxies."""
        return len(self.proxies)
