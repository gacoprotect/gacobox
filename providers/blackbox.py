"""Blackbox.ai client driven entirely through Playwright.

The signup flow uses Next.js server actions (multipart POST /signup) that
require a real browser context. httpx cannot reproduce it reliably — all
browser interactions here go through Playwright in ONE browser session so
cookies persist from signup through key creation.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse

from playwright.async_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from config import Config
from logger import get_logger
from providers import tempmail
from providers import cloudflare_tempmail
from providers import domain_cooldown


class BlackboxError(Exception):
    """Raised when a browser step in the Blackbox flow fails."""


def _mask_proxy(proxy: str | None) -> str:
    """Render a proxy URL for logs with the user:pass part hidden.

    Only the userinfo is masked; scheme, host and port stay readable because
    they are what you need when a run stalls on one endpoint.
    """
    if not proxy:
        return "direct"
    parsed = urlparse(proxy)
    if not parsed.username:
        return proxy
    host = parsed.hostname or ""
    if parsed.port:
        host += f":{parsed.port}"
    return f"{parsed.scheme}://***@{host}"


@dataclass(slots=True)
class AccountResult:
    """Outcome of one full signup+key run."""

    email: str = ""
    password: str = ""
    api_key: str = ""
    error: str = ""
    success: bool = False
    elapsed: float = 0.0


# Next.js server action payload captured from the real browser:
#   0 = ["$undefined","$K1"]
_SIGNUP_FIELDS = ("1_email", "1_password", "0")


class BlackboxClient:
    """Owns one Playwright browser/context/page for the whole account flow."""

    def __init__(self, cfg: Config, proxy: str | None = None) -> None:
        self._cfg = cfg
        self._proxy = proxy
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._key_created: asyncio.Event = asyncio.Event()
        self._api_key: str = ""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        
        launch_options = {"headless": self._cfg.headless}
        if self._proxy:
            # Chromium ignores user:pass inside the proxy URL and stalls on the
            # auth prompt, so credentials must be passed as separate fields.
            parsed = urlparse(self._proxy)
            server = f"{parsed.scheme}://{parsed.hostname}"
            if parsed.port:
                server += f":{parsed.port}"
            proxy_opts: dict[str, str] = {"server": server}
            if parsed.username:
                proxy_opts["username"] = unquote(parsed.username)
            if parsed.password:
                proxy_opts["password"] = unquote(parsed.password)
            launch_options["proxy"] = proxy_opts
        
        self._browser = await self._playwright.chromium.launch(**launch_options)
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()

        log = get_logger()
        # A proxy credential prompt surfaces as a native dialog, which would
        # otherwise block silently until the OTP wait times out.
        self._page.on(
            "dialog",
            lambda d: log.warning("DIALOG %s: %s", d.type, d.message),
        )
        self._page.on(
            "requestfailed",
            lambda r: self._log_request_failure(r),
        )

    def _log_request_failure(self, request) -> None:
        # Third-party trackers and cancelled Next.js prefetches fail constantly
        # and would bury real errors; only same-origin document loads matter.
        log = get_logger()
        failure = request.failure or ""
        own_origin = request.url.startswith(self._cfg.blackbox_url)
        if own_origin and "_rsc=" not in request.url and "ERR_ABORTED" not in failure:
            log.warning("REQ FAILED %s %s", failure, request.url[:120])
        else:
            log.debug("req failed (ignorable) %s %s", failure, request.url[:120])

    async def stop(self) -> None:
        try:
            if self._browser is not None:
                await self._browser.close()
        finally:
            self._browser = None
            self._context = None
            self._page = None
            if self._playwright is not None:
                await self._playwright.stop()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise BlackboxError("Client not started")
        return self._page

    # ------------------------------------------------------------------
    # Full flow
    # ------------------------------------------------------------------

    async def _snapshot(self, email: str, tag: str) -> None:
        """Log what the browser actually shows, plus a PNG for the hard cases."""
        log = get_logger()
        page = self._page
        if page is None:
            log.error("[%s] %s: no page", email, tag)
            return
        try:
            body = await page.evaluate("document.body ? document.body.innerText : ''")
            body = " | ".join(line.strip() for line in body.splitlines() if line.strip())
            log.error(
                "[%s] %s url=%s title=%r inputs=%d otp_input=%d buttons=%d bodylen=%d",
                email,
                tag,
                page.url,
                await page.title(),
                await page.locator("input").count(),
                await page.locator("input[maxlength='6']").count(),
                await page.locator("button").count(),
                len(body),
            )
            log.error("[%s] %s body: %s", email, tag, body[:600])
            shot = Path(self._cfg.output_dir) / "debug" / f"{tag}_{email.split('@')[0]}.png"
            shot.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(shot))
            log.error("[%s] %s screenshot=%s", email, tag, shot)
        except Exception as exc:
            log.error("[%s] %s: snapshot failed: %s", email, tag, exc)

    async def register_and_create_key(
        self,
        email: str,
        password: str,
        jwt_token: str = "",
        on_stage: Callable[[str], None] | None = None,
    ) -> str:
        """Run the entire verified flow and return the sk-... API key.

        Steps:
          1. Open /signup, fill email+password, submit (server action POST /signup)
          2. Wait for the OTP email, enter the code, click Verify
          3. Land on /activity, navigate to /keys
          4. Click CREATE KEY, name it, confirm, read the key from the modal
          5. Click DONE to close the modal
        """
        page = self.page
        page.set_default_timeout(self._cfg.request_timeout * 1000)

        log = get_logger()
        log.info("[%s] flow start proxy=%s", email, _mask_proxy(self._proxy))
        stage = on_stage or (lambda _: None)

        stage("registering")
        await self.signup(email, password)
        log.info("[%s] signup submitted, url=%s", email, page.url)

        stage("waiting_verify")
        code = await self._await_otp_with_resend(email, jwt_token, stage)
        log.info("[%s] otp received=%s", email, code)

        stage("verifying_otp")
        await self.verify_otp(code, email)
        log.info("[%s] otp verified, url=%s", email, page.url)

        stage("creating_key")
        try:
            api_key = await self.create_api_key()
        except Exception:
            await self._snapshot(email, "no_key")
            raise
        log.info("[%s] key created len=%d", email, len(api_key))
        return api_key

    # ------------------------------------------------------------------
    # Step 1 — signup
    # ------------------------------------------------------------------

    async def signup(self, email: str, password: str) -> None:
        page = self.page
        log = get_logger()

        # Through a rotating proxy the HTML shell sometimes arrives without the
        # Next.js bundle executing, leaving a titled but empty page with no form.
        email_input = page.locator('input[type="email"], input[name="email"]').first
        for attempt in range(1, 4):
            await page.goto(f"{self._cfg.blackbox_url}/signup", wait_until="domcontentloaded")
            try:
                await email_input.wait_for(state="visible", timeout=20_000)
                break
            except PlaywrightTimeoutError:
                log.warning(
                    "[%s] signup form not rendered (attempt %d/3), reloading", email, attempt
                )
                if attempt == 3:
                    await self._snapshot(email, "no_signup_form")
                    raise BlackboxError("Signup form never rendered after 3 attempts")

        await email_input.fill(email)

        pass_input = page.locator('input[type="password"], input[name="password"]').first
        await pass_input.wait_for(state="visible", timeout=10_000)
        await pass_input.fill(password)

        # The form is a Next.js server action — clicking the submit button
        # fires the multipart POST /signup captured in the network log.
        submit = page.locator('button[type="submit"]').first
        await submit.click()

        # Give the server action a moment to round-trip before the OTP screen.
        await _wait_any(
            page,
            ["text=Verify", "input[maxlength='6']", "text=verification", "text=code"],
            timeout=15_000,
            hint="OTP screen after signup",
        )

    # ------------------------------------------------------------------
    # Step 2 — OTP verification
    # ------------------------------------------------------------------

    async def _await_otp_with_resend(
        self,
        email: str,
        jwt_token: str,
        stage: Callable[[str], None] | None = None,
    ) -> str:
        """Poll the mailbox in rounds, clicking Resend between empty rounds.

        Blackbox drops a fair number of first-attempt mails, so a single long
        wait mostly measures how patient we are. Each round re-asks for the
        code, which is what a human staring at the form would do.
        """
        rounds = max(1, self._cfg.otp_resend_attempts)
        log = get_logger()
        emit = stage or (lambda _: None)
        last_exc: Exception | None = None
        used = 0
        resend_blocked = False

        for attempt in range(1, rounds + 1):
            used = attempt
            emit("waiting_verify" if attempt == 1 else f"resend {attempt}/{rounds}")
            try:
                if self._cfg.tempmail_provider == "cloudflare":
                    return await cloudflare_tempmail.wait_for_otp(
                        self._cfg.cloudflare_api_url,
                        jwt_token,
                        email,
                        self._cfg,
                    )
                return await tempmail.wait_for_otp(email, self._cfg)
            except Exception as exc:
                last_exc = exc
                log.warning(
                    "[%s] no otp on round %d/%d: %s", email, attempt, rounds, exc
                )
                await self._snapshot(email, f"no_otp_round{attempt}")
                if attempt == rounds:
                    break
                if not await self._resend_with_retry(email):
                    resend_blocked = True
                    break

        await self._snapshot(email, "no_otp")
        domain = email.partition("@")[2]
        if resend_blocked:
            # The mailbox never got a chance: the send endpoint refused us, and
            # those 500s hit ten different domains in one run, including two
            # that succeeded minutes later. Benching here would retire healthy
            # domains for an outage on Blackbox's side.
            log.error(
                "[%s] giving up after %d/%d round(s): resend endpoint refused, "
                "not benching %s",
                email,
                used,
                rounds,
                domain,
            )
        elif domain:
            secs = domain_cooldown.penalize(domain)
            log.error(
                "[%s] no otp after %d/%d round(s) - benching %s for %.0f min",
                email,
                used,
                rounds,
                domain,
                secs / 60,
            )
        raise last_exc if last_exc else BlackboxError("OTP wait failed")

    async def _click_resend(self, email: str) -> bool:
        """Click Resend and confirm the server actually accepted it.

        A click that raises nothing only proves Playwright found the element.
        The button can be disabled behind a cooldown, or the POST can come back
        429/4xx, and either way the old code reported success and then waited
        another full round for a mail that was never sent. So we wait for the
        response the click triggers and judge on its status.
        """
        log = get_logger()
        page = self.page
        button = page.locator('button:has-text("Resend")').first
        try:
            if not await button.is_visible():
                log.warning("[%s] resend button not visible, giving up", email)
                return False
            if not await button.is_enabled():
                text = (await button.inner_text()).strip()
                log.warning(
                    "[%s] resend button disabled (label=%r), server is rate limiting",
                    email,
                    text,
                )
                return False

            async with page.expect_response(
                lambda r: r.request.method == "POST"
                and r.url.startswith(self._cfg.blackbox_url),
                timeout=15_000,
            ) as caught:
                await button.click()
            resp = await caught.value
        except PlaywrightTimeoutError:
            # Click landed but nothing left the page: no request means no mail.
            log.error(
                "[%s] resend click produced no POST within 15s - treating as failed",
                email,
            )
            await self._snapshot(email, "resend_no_request")
            return False
        except PlaywrightError as exc:
            log.warning("[%s] resend click failed: %s", email, exc)
            return False

        body = ""
        try:
            body = (await resp.text())[:300]
        except PlaywrightError:
            pass

        if resp.status >= 400:
            log.error(
                "[%s] resend rejected: HTTP %d %s body=%s",
                email,
                resp.status,
                resp.url[:120],
                body,
            )
            await self._snapshot(email, f"resend_http{resp.status}")
            return False

        log.info(
            "[%s] resend accepted: HTTP %d %s body=%s",
            email,
            resp.status,
            resp.url[:120],
            body,
        )
        await self._log_visible_alert(email)
        return True

    async def _resend_with_retry(self, email: str, attempts: int = 3) -> bool:
        """Retry a rejected resend before giving up on the address.

        The 500s are not tied to a domain or to timing: one run had the same
        domain accepted once and rejected once, and every request sat at the
        same 126s mark. Roughly two thirds fail, so a single rejection says
        nothing about the next attempt.
        """
        log = get_logger()
        for attempt in range(1, attempts + 1):
            if await self._click_resend(email):
                return True
            if attempt < attempts:
                delay = 2.0 * attempt
                log.info(
                    "[%s] resend attempt %d/%d rejected, retrying in %.0fs",
                    email,
                    attempt,
                    attempts,
                    delay,
                )
                await asyncio.sleep(delay)
        log.error("[%s] resend failed %d times, giving up", email, attempts)
        return False

    async def _log_visible_alert(self, email: str) -> None:
        """Surface any on-page message the resend produced.

        Blackbox reports 'too many requests' as ordinary text, not an HTTP
        error, so a 200 alone does not mean a mail went out.
        """
        log = get_logger()
        try:
            text = await self.page.evaluate(
                """() => {
                    const hits = [];
                    const nodes = document.querySelectorAll(
                        '[role=alert], [class*=toast], [class*=error], [class*=alert]'
                    );
                    for (const n of nodes) {
                        const t = (n.innerText || '').trim();
                        if (t) hits.push(t);
                    }
                    return hits.join(' | ');
                }"""
            )
        except PlaywrightError as exc:
            log.debug("[%s] could not read page alerts: %s", email, exc)
            return
        if text:
            log.warning("[%s] page message after resend: %s", email, text[:300])

    async def verify_otp(self, code: str, email: str = "") -> None:
        page = self.page
        otp_input = page.locator('input[maxlength="6"], input[placeholder*="code" i], input[name="code"], input[inputmode="numeric"]').first
        try:
            await otp_input.wait_for(state="visible", timeout=15_000)
        except PlaywrightTimeoutError:
            # Some signups land on a "check your email" page instead of the code
            # form, so the OTP arrives with nowhere to type it.
            await self._snapshot(email, "no_otp_form")
            raise
        await otp_input.fill(code)

        verify_btn = page.locator('button:has-text("Verify")').first
        await verify_btn.click()

        # After verification the app auto-logs-in and lands on /activity.
        # wait_for_url's default 'load' event can stall on the SPA, so poll.
        deadline = asyncio.get_event_loop().time() + 45
        while asyncio.get_event_loop().time() < deadline:
            if re.search(r"/(activity|dashboard)", page.url):
                return
            await asyncio.sleep(0.5)
        raise BlackboxError(f"Did not reach /activity after OTP verify (still at {page.url})")

    # ------------------------------------------------------------------
    # Step 3 — API key creation
    # ------------------------------------------------------------------

    async def create_api_key(self, name: str | None = None) -> str:
        key_name = name or self._cfg.key_name
        page = self.page

        # Listen for the key POST response in case the modal read-back fails.
        self._key_created = asyncio.Event()
        self._api_key = ""
        page.on(
            "response",
            lambda r: asyncio.create_task(self._capture_key_response(r)),
        )

        await page.goto(f"{self._cfg.blackbox_url}/keys", wait_until="domcontentloaded")
        create_btn = page.locator('button:has-text("CREATE KEY")').first
        await create_btn.wait_for(state="visible", timeout=30_000)
        await create_btn.click()

        # Modal appears with a key-name input (placeholder "e.g. Production")
        # and a disabled "Create API Key" button until a name is entered.
        name_locator = page.locator(
            'input[placeholder*="Production"], input[placeholder*="Key name"], input[placeholder*="e.g."]'
        ).first
        await name_locator.wait_for(state="visible", timeout=15_000)
        await name_locator.fill(key_name)

        confirm_btn = page.locator('button:has-text("CREATE API KEY"), button:has-text("Create API Key")').first
        await confirm_btn.wait_for(state="visible", timeout=15_000)
        # The button starts disabled and enables once the name is non-empty;
        # wait for it to become enabled before clicking.
        await page.wait_for_function(
            """() => {
                const btns = [...document.querySelectorAll('button')];
                return btns.some(b => /create api key/i.test(b.textContent || '') && !b.disabled);
            }""",
            timeout=15_000,
        )
        await confirm_btn.click()

        # The key appears in a modal. Prefer reading it from the network
        # response, then fall back to scanning the page text.
        api_key = ""
        try:
            await asyncio.wait_for(self._key_created.wait(), timeout=60)
            api_key = self._api_key
        except asyncio.TimeoutError:
            # The button still read "CREATING…" when this timed out at 15s, so
            # the POST was in flight rather than lost; the old budget was just
            # short of what a slow server needs.
            get_logger().warning(
                "key POST did not return within 60s, reading the page instead"
            )

        if not api_key:
            api_key = await self._read_key_from_page()

        if not api_key:
            raise BlackboxError("API key not found after creation")

        await self._close_key_modal()
        return api_key

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _capture_key_response(self, response: object) -> None:
        try:
            url = response.url
            if url.endswith("/api/v0/keys") or "/api/v0/keys?" in url:
                if response.request.method == "POST":
                    body = await response.text()
                    match = re.search(r'"(?:api_key|key|token)"\s*:\s*"([^"]+)"', body)
                    if match:
                        self._api_key = match.group(1)
                        self._key_created.set()
        except Exception:
            pass

    async def _read_key_from_page(self) -> str:
        page = self.page
        for _ in range(5):
            text = await page.locator("body").inner_text()
            for pattern in (r"sk-[A-Za-z0-9_-]{12,}", r"\b(?:bb_|sk_)[A-Za-z0-9_-]{16,}\b"):
                match = re.search(pattern, text)
                if match:
                    return match.group(0)
            await asyncio.sleep(1)
        return ""

    async def _close_key_modal(self) -> None:
        page = self.page
        done = page.locator('button:has-text("DONE"), button:has-text("Done"), button:has-text("Close")').first
        try:
            await done.click(timeout=5_000)
        except PlaywrightTimeoutError:
            # Modal already closed or no close button — nothing to do.
            pass


async def _wait_any(
    page: Page,
    selectors: list[str],
    *,
    timeout: int,
    hint: str,
) -> None:
    """Wait until any of the selectors matches, or raise BlackboxError."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        for sel in selectors:
            locator = page.locator(sel)
            try:
                if await locator.count() > 0 and await locator.first.is_visible():
                    return
            except Exception:
                continue
        await asyncio.sleep(0.5)
    raise BlackboxError(f"Timed out waiting for {hint}")
