"""
ServiceNow Playbook Testing — Python + Playwright GUI Test Framework
===================================================================
E2E browser automation for ServiceNow Playbook workflows using Playwright.

Supports:
  - Login via browser (handles MFA, SSO, okta, MFA)
  - Record creation & Playbook triggering
  - Stage polling via UI (watching DOM changes)
  - Screenshot on every assertion for rich CI/CD reports
  - HTML report export via pytest-html
"""

from __future__ import annotations

import time
import os
import re
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext, Playwright

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PlaywrightConfig:
    """Playwright/Servicenow client configuration."""
    instance_url: str
    username: str
    password: str
    headless: bool = True
    slow_mo: int = 0          # ms between Playwright actions (debugging)
    timeout: int = 30_000     # page timeout ms
    screenshot_dir: str = "screenshots"
    browser_type: str = "chromium"  # chromium | firefox | webkit

    # selectors
    login_username_input: str = "#user_name"
    login_password_input: str = "#user_password"
    login_submit_button: str = "#sysverb_login"
    login_mfa_input: str = "input[name='otp']"
    frame_container: str = "iframe[name='gsft_main']"
    incident_list_view: str = "table#incident tbody tr"
    record_stage_badge: str = "[data-type='badge'][data-id='stage']"
    stage_label: str = ".workflow-stage-label"

    def base_url(self) -> str:
        return self.instance_url.rstrip("/")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class ServiceNowPlaywrightClient:
    """
    Playwright-powered browser client for ServiceNow Playbook E2E testing.

    Usage::

        client = ServiceNowPlaywrightClient(cfg)
        with client.authenticated_context() as ctx:
            page = ctx.new_page()
            # ... interact
    """

    def __init__(self, config: PlaywrightConfig):
        self.cfg = config
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> "ServiceNowPlaywrightClient":
        self._playwright = sync_playwright().start()
        return self

    def stop(self) -> None:
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    @property
    def browser(self) -> Browser:
        if self._browser is None:
            raise RuntimeError("Call start() first.")
        return self._browser

    def new_context(self, **kwargs) -> BrowserContext:
        """Create a new incognito-ish browser context (no cache, no cookies)."""
        defaults = {
            "viewport": {"width": 1440, "height": 900},
            "ignore_https_errors": True,
            "record_video_dir": None,
        }
        defaults.update(kwargs)
        return self.browser.new_context(**defaults)

    def authenticated_context(self, **kwargs) -> AuthenticatedContext:
        """
        Yields an AuthenticatedContext: a BrowserContext already logged in.
        Usage as context manager — handles teardown automatically.

        Example::

            with client.authenticated_context() as ctx:
                page = ctx.new_page()
                page.goto(...)
        """
        ctx = self.new_context(**kwargs)
        return AuthenticatedContext(ctx, self.cfg)

    # ------------------------------------------------------------------
    # Playwright getter (for advanced use)
    # ------------------------------------------------------------------

    @property
    def playwright(self) -> Playwright:
        if self._playwright is None:
            raise RuntimeError("Call start() first.")
        return self._playwright


# ---------------------------------------------------------------------------
# Authenticated context
# ---------------------------------------------------------------------------

class AuthenticatedContext:
    """
    A BrowserContext that is logged into ServiceNow.
    Exposes page factory and helper methods.
    """

    def __init__(self, context: BrowserContext, cfg: PlaywrightConfig):
        self._ctx = context
        self.cfg = cfg

    def __enter__(self) -> "AuthenticatedContext":
        return self

    def __exit__(self, *args) -> None:
        self._ctx.close()

    def new_page(self) -> Page:
        """Create a new tab (page) inside this context."""
        return self._ctx.new_page()

    def login(self) -> Page:
        """
        Perform full login flow (standard | MFA | okta/SSO).
        Returns the page after login completes.
        """
        cfg = self.cfg
        page = self._ctx.new_page()
        page.goto(f"{cfg.base_url()}/login.do", timeout=cfg.timeout)

        # ── Standard ServiceNow login ──────────────────────────────────
        if page.is_visible(cfg.login_username_input, timeout=5_000):
            page.fill(cfg.login_username_input, cfg.username)
            page.fill(cfg.login_password_input, cfg.password)
            page.click(cfg.login_submit_button)
            page.wait_for_load_state("networkidle", timeout=cfg.timeout)

        # ── MFA (duo / TOTP) ───────────────────────────────────────────
        if page.is_visible(cfg.login_mfa_input, timeout=5_000):
            mfa_token = os.environ.get("SN_MFA_TOKEN", "")
            if not mfa_token:
                raise RuntimeError(
                    "MFA detected but SN_MFA_TOKEN env var is not set."
                )
            page.fill(cfg.login_mfa_input, mfa_token)
            page.click(cfg.login_submit_button)
            page.wait_for_load_state("networkidle", timeout=cfg.timeout)

        # ── okta / SSO redirect ─────────────────────────────────────────
        if "okta" in page.url.lower() or page.title().lower().contains("okta"):
            self._handle_okta(page)

        # ── Main ServiceNow frame ──────────────────────────────────────
        # ServiceNow often loads the app inside a gsft_main iframe.
        # Switch to it if present.
        try:
            frame = page.frame(cfg.frame_container)
            if frame is not None:
                page = frame
        except Exception:
            pass

        page.wait_for_load_state("networkidle", timeout=cfg.timeout)
        return page

    def _handle_okta(self, page: Page) -> None:
        """Handle okta SSO redirect if detected."""
        page.wait_for_load_state("load")
        # okta uses input[name='identifier'] and input[name='password']
        if page.is_visible("input[name='identifier']", timeout=15_000):
            page.fill("input[name='identifier']", self.cfg.username)
            page.click("button[type='submit']")
            page.wait_for_timeout(2_000)
        if page.is_visible("input[name='password']", timeout=10_000):
            page.fill("input[name='password']", self.cfg.password)
            page.click("button[type='submit']")
            page.wait_for_load_state("networkidle", timeout=self.cfg.timeout)

    # ------------------------------------------------------------------
    # Page helpers
    # ------------------------------------------------------------------

    @staticmethod
    def screenshot(page: Page, name: str, dir: str = "screenshots") -> str:
        """Take a screenshot and return the file path."""
        Path(dir).mkdir(parents=True, exist_ok=True)
        path = os.path.join(dir, f"{name}.png")
        page.screenshot(path=path, full_page=True)
        return path

    @staticmethod
    def wait_for_stage(
        page: Page,
        stage_name: str,
        timeout: int = 180_000,
        interval: float = 2.0,
        stage_badge_selector: str = ".workflow-stage-label",
        exact: bool = False,
    ) -> bool:
        """
        Poll the DOM until the Playbook stage label matches stage_name.

        Returns True if matched; raises TimeoutError on timeout.
        """
        deadline = time.time() + timeout / 1000
        while time.time() < deadline:
            try:
                el = page.wait_for_selector(
                    stage_badge_selector, state="visible", timeout=5_000
                )
                text = el.inner_text().strip() if el else ""
                if exact:
                    matched = text == stage_name
                else:
                    matched = stage_name.lower() in text.lower()
                if matched:
                    return True
            except Exception:
                pass
            time.sleep(interval)
        raise TimeoutError(
            f"Stage '{stage_name}' never appeared within {timeout}ms. "
            f"Last URL: {page.url}"
        )


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def playwright_config() -> PlaywrightConfig:
    """
    Build PlaywrightConfig from environment variables.

    Variables required:
      SN_INSTANCE   — e.g. https://dev12345.service-now.com
      SN_USER       — username
      SN_PASS       — password

    Variables optional:
      SN_MFA_TOKEN  — OTP code if MFA is enabled
      HEADLESS      — true/false (default true)
      BROWSER_TYPE  — chromium|firefox|webkit (default chromium)
      SLOW_MO       — ms between actions (debug, default 0)
      SCREENSHOT_DIR — directory for screenshots (default screenshots)
    """
    missing = []
    for var in ("SN_INSTANCE", "SN_USER", "SN_PASS"):
        if not os.environ.get(var):
            missing.append(var)
    if missing:
        pytest.fail(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    return PlaywrightConfig(
        instance_url=os.environ["SN_INSTANCE"],
        username=os.environ["SN_USER"],
        password=os.environ["SN_PASS"],
        headless=os.environ.get("HEADLESS", "true").lower() != "false",
        slow_mo=int(os.environ.get("SLOW_MO", "0")),
        timeout=int(os.environ.get("SN_TIMEOUT", "30000")),
        screenshot_dir=os.environ.get("SCREENSHOT_DIR", "screenshots"),
        browser_type=os.environ.get("BROWSER_TYPE", "chromium"),
    )


@pytest.fixture(scope="session")
def sn_client(playwright_config: PlaywrightConfig) -> ServiceNowPlaywrightClient:
    """Session-scoped Playwright client — started once per test session."""
    cfg = playwright_config
    client = ServiceNowPlaywrightClient(cfg)
    client.start()

    # Launch browser
    browser_kwargs: dict = {
        "headless": cfg.headless,
        "slow_mo": cfg.slow_mo,
    }
    if cfg.browser_type == "firefox":
        client._browser = client.playwright.firefox.launch(**browser_kwargs)
    elif cfg.browser_type == "webkit":
        client._browser = client.playwright.webkit.launch(**browser_kwargs)
    else:
        client._browser = client.playwright.chromium.launch(**browser_kwargs)

    yield client

    client.stop()


@pytest.fixture(scope="function")
def authenticated_page(sn_client: ServiceNowPlaywrightClient) -> Page:
    """
    Function-scoped fixture: logs in and returns a fresh page.
    Each test gets its own incognito page.
    """
    with sn_client.authenticated_context() as ctx:
        page = ctx.login()
        yield page
        # teardown: close page
        page.close()
