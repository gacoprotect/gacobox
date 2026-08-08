"""Cloudflare Workers temporary mailbox client.

Every request here passes trust_env=False: the browser proxies are for looking
like different users to Blackbox, and routing our own mailbox through a rotating
exit node only adds latency and failure modes to the OTP poll.
"""
from __future__ import annotations

import re
import time
from typing import Any

import httpx

from config import Config
from logger import get_logger

_OTP_PATTERN = re.compile(r"\b(\d{6})\b")


class CloudflareTempMailError(Exception):
    """Raised when no OTP arrives in time or the mailbox API fails."""


async def create_address(api_url: str, domain: str, *, timeout: int = 30) -> tuple[str, str]:
    """Create a new temporary email address via Cloudflare Workers API.
    
    Returns (email_address, jwt_token).
    """
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        payload = {
            "name": "",
            "cf_token": "",
            "enableRandomSubdomain": False
        }
        
        if domain:
            payload["domain"] = domain
        else:
            payload["domain"] = ""
        
        resp = await client.post(
            f"{api_url}/api/new_address",
            json=payload,
        )
        
        if resp.status_code >= 400:
            raise CloudflareTempMailError(
                f"Failed to create address: {resp.status_code} {resp.text}"
            )
        
        data = resp.json()
        
        # Response format: {"jwt": "...", "address": "..."}
        if not isinstance(data, dict):
            raise CloudflareTempMailError(f"Invalid response format: {data}")
        
        jwt_token = data.get("jwt")
        address = data.get("address")
        
        if not jwt_token or not address:
            raise CloudflareTempMailError(f"Missing jwt or address in response: {data}")
        
        return address, jwt_token


async def fetch_messages(
    api_url: str, 
    jwt_token: str, 
    *, 
    timeout: int = 30
) -> list[dict[str, Any]]:
    """Fetch messages for a mailbox using JWT token.
    
    Returns list of messages or [] on failure.
    """
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        resp = await client.get(
            f"{api_url}/api/parsed_mails",
            params={"limit": 20, "offset": 0},
            headers={
                "Authorization": f"Bearer {jwt_token}"
            },
        )
        
        if resp.status_code >= 400:
            return []
        
        data = resp.json()
        
        # Response format: {"results": [...]}
        if isinstance(data, dict):
            results = data.get("results")
            if isinstance(results, list):
                return results  # type: ignore[return-value]
        
        if isinstance(data, list):
            return data  # type: ignore[return-value]
        
        return []


async def read_message(
    api_url: str,
    message_id: str,
    jwt_token: str,
    *,
    timeout: int = 30
) -> dict[str, Any]:
    """Fetch a single message body."""
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        resp = await client.get(
            f"{api_url}/api/parsed_mail/{message_id}",
            headers={
                "Authorization": f"Bearer {jwt_token}"
            },
        )
        
        if resp.status_code >= 400:
            return {}
        
        data = resp.json()
        return data if isinstance(data, dict) else {}


def extract_otp(message: dict[str, Any]) -> str | None:
    """Extract 6-digit OTP from a parsed mail row.

    Field order matches /api/parsed_mail output: text is already decoded, html is
    the fallback, subject sometimes carries the code on its own.
    """
    for key in ("text", "html", "subject", "message", "raw"):
        value = message.get(key)
        if not isinstance(value, str):
            continue
        match = _OTP_PATTERN.search(value)
        if match:
            return match.group(1)

    return None


async def wait_for_otp(
    api_url: str,
    jwt_token: str,
    email: str,
    cfg: Config
) -> str:
    """Poll Cloudflare Workers temp email API until a 6-digit OTP arrives.
    
    Returns the code, or raises CloudflareTempMailError.
    """
    # The initial delay must not eat into the poll budget.
    await _sleep(5)
    deadline = time.monotonic() + cfg.verify_poll_timeout
    
    while True:
        messages = await fetch_messages(api_url, jwt_token, timeout=cfg.request_timeout)
        
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            
            # Try to extract OTP directly from list response
            code = extract_otp(msg)
            if code:
                return code
            
            # If no OTP in list, fetch full message
            msg_id = msg.get("id") or msg.get("_id") or msg.get("message_id")
            if msg_id is None:
                continue
            
            full = await read_message(
                api_url, 
                str(msg_id), 
                jwt_token, 
                timeout=cfg.request_timeout
            )
            code = extract_otp(full)
            if code:
                return code
        
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CloudflareTempMailError(
                f"No OTP received within {cfg.verify_poll_timeout}s"
            )

        nap = min(cfg.verify_poll_interval, remaining)
        get_logger().debug(
            "[%s] poll: %d msg(s), no otp, %.0fs left, sleeping %.0fs",
            email,
            len(messages),
            remaining,
            nap,
        )
        await _sleep(nap)


async def _sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(max(0.1, seconds))
