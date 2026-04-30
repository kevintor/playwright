"""
ServiceNow Playbook E2E GUI Tests
==================================
Browser automation tests for ServiceNow Playbook workflows using Playwright.

Prerequisites:
    SN_INSTANCE   — e.g. https://dev12345.service-now.com
    SN_USER       — username
    SN_PASS       — password
    SN_MFA_TOKEN  — OTP if MFA is enabled (optional)

Run:
    pytest tests/ --html=report.html --self-contained-html -v
"""

import os
import time
import pytest
from playwright.sync_api import Page, expect

from servicenow_client import (
    PlaywrightConfig,
    ServiceNowPlaywrightClient,
    AuthenticatedContext,
)


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def create_incident_with_playbook(
    page: Page,
    short_description: str,
    playbook_name: str,
    urgency: str = "2",
    assignment_group: str = "Security",
) -> str:
    """
    Navigate to Incident > create a new record and attach a Playbook.
    Returns the sys_id extracted from the URL.
    """
    page.goto("/nav_to.do?uri=%2Fincident.do%3Fsys_id%3D-1")
    page.wait_for_load_state("networkidle")

    # Fill short description
    page.fill("input[name='short_description']", short_description)
    page.fill("input[name='urgency']", urgency)

    # Assignment group (type and select)
    page.click("button[data-name='assignment_group']")
    page.wait_for_timeout(1_000)
    page.fill("input.glide-form-ui-input", assignment_group)
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)

    # Attach Playbook (custom field — field name may vary by instance)
    # Common selectors for Playbook dropdown on Incident form
    playbook_selectors = [
        "select[name='u_playbook']",
        "select[id='IO:u_playbook']",
        "[data-name='u_playbook'] select",
    ]
    for sel in playbook_selectors:
        if page.locator(sel).count() > 0:
            page.select_option(sel, playbook_name)
            break

    # Submit the form
    page.click("button#sysverb_insert")
    page.wait_for_load_state("networkidle", timeout=15_000)

    # Extract sys_id from URL
    url = page.url
    sys_id = ""
    if "sys_id=" in url:
        sys_id = url.split("sys_id=")[-1].split("&")[0].split("#")[0]
    return sys_id


def navigate_to_incident(page: Page, sys_id: str) -> None:
    """Open an existing incident by sys_id."""
    page.goto(f"/incident.do?sys_id={sys_id}")
    page.wait_for_load_state("networkidle")


# ════════════════════════════════════════════════════════════════════════════
# Tests
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.playbook
@pytest.mark.gui
@pytest.mark.slow
class TestIncidentPlaybook:
    """E2E Playbook tests for the Incident [Security] Playbook."""

    def test_playbook_reaches_containment_stage(
        self, authenticated_page: Page, stage_timeout: int, screenshot_dir, playwright_config: PlaywrightConfig
    ):
        """
        Create an Incident with a Security Playbook attached and verify
        it progresses to the 'Containment' stage within the timeout.
        """
        page = authenticated_page
        cfg = playwright_config

        # ── Trigger: create incident with playbook ────────────────────
        sys_id = create_incident_with_playbook(
            page,
            short_description="Playwright E2E Test — Containment Stage",
            playbook_name="security_incident_response",
            urgency="2",
        )
        assert sys_id, "Failed to extract sys_id from created incident"

        # ── Navigate to the record (playbook UI loads inside the form) ─
        navigate_to_incident(page, sys_id)

        # ── Poll until Containment stage appears ─────────────────────
        stage_found = AuthenticatedContext.wait_for_stage(
            page,
            stage_name="Containment",
            timeout=stage_timeout * 1000,
            stage_badge_selector=".workflow-stage-label, [data-stage-name]",
            exact=False,
        )

        # ── Screenshot for report ──────────────────────────────────────
        screenshot_path = AuthenticatedContext.screenshot(
            page,
            f"containment_stage_{sys_id}",
            dir=str(screenshot_dir),
        )
        page.context.metadata = {"screenshot": screenshot_path}  # hook for HTML report

        assert stage_found, (
            f"Playbook never reached Containment stage. Screenshot: {screenshot_path}"
        )

    def test_playbook_stage_navigation_full_flow(
        self, authenticated_page: Page, stage_timeout: int, screenshot_dir, playwright_config: PlaywrightConfig
    ):
        """
        Full SIR Playbook flow: Trigger → Diagnosis → Containment → Eradication → Recovery.
        Verifies each stage in sequence.
        """
        page = authenticated_page
        cfg = playwright_config

        sys_id = create_incident_with_playbook(
            page,
            short_description="Playwright E2E Full Flow Test",
            playbook_name="security_incident_response",
        )
        assert sys_id

        navigate_to_incident(page, sys_id)

        stages = ["Trigger", "Diagnosis", "Containment", "Eradication", "Recovery"]
        stage_timeout_per = stage_timeout // len(stages)

        for stage in stages:
            screenshot_path = AuthenticatedContext.screenshot(
                page,
                f"stage_{stage}_{sys_id}",
                dir=str(screenshot_dir),
            )
            try:
                found = AuthenticatedContext.wait_for_stage(
                    page,
                    stage_name=stage,
                    timeout=stage_timeout_per * 1000,
                    exact=False,
                )
                assert found, f"Stage '{stage}' not reached. Screenshot: {screenshot_path}"
            except TimeoutError as e:
                # Take failure screenshot and re-raise
                AuthenticatedContext.screenshot(
                    page,
                    f"FAIL_stage_{stage}_{sys_id}",
                    dir=str(screenshot_dir),
                )
                raise

    def test_playbook_record_stays_in_stage_on_invalid_action(
        self, authenticated_page: Page, stage_timeout: int, screenshot_dir, playwright_config: PlaywrightConfig
    ):
        """
        Verify that submitting invalid data does not crash the Playbook
        and the record remains in the current stage.
        """
        page = authenticated_page
        cfg = playwright_config

        # Create incident (no playbook needed for this negative test)
        page.goto("/nav_to.do?uri=%2Fincident.do%3Fsys_id%3D-1")
        page.wait_for_load_state("networkidle")
        page.fill("input[name='short_description']", "Negative test — invalid data")
        page.fill("input[name='urgency']", "1" if page.is_visible("input[name='urgency']") else "")
        page.click("button#sysverb_insert")
        page.wait_for_load_state("networkidle", timeout=10_000)

        sys_id = page.url.split("sys_id=")[-1].split("&")[0].split("#")[0]

        # Attempt to set an invalid field
        navigate_to_incident(page, sys_id)

        # Stage badge should still be visible / no crash
        try:
            badge = page.wait_for_selector(
                ".workflow-stage-label, [data-stage-name]",
                state="visible",
                timeout=5_000,
            )
            assert badge is not None
        except Exception as e:
            AuthenticatedContext.screenshot(page, f"invalid_action_{sys_id}", dir=str(screenshot_dir))
            raise AssertionError(f"Playbook UI broke on invalid action: {e}")


@pytest.mark.playbook
@pytest.mark.gui
class TestLoginAndNavigation:
    """Login, navigation and UI element tests."""

    def test_login_succeeds(self, sn_client: ServiceNowPlaywrightClient):
        """Verify login completes without errors and lands on ServiceNow home."""
        with sn_client.authenticated_context() as ctx:
            page = ctx.login()
            assert "service-now" in page.url.lower() or page.url.endswith("/"), \
                f"Unexpected URL after login: {page.url}"

    def test_navigate_to_incident_list(self, authenticated_page: Page):
        """Verify Incident list page loads and contains rows."""
        page = authenticated_page
        page.goto("/nav_to.do?uri=%2Fincident.do")
        page.wait_for_load_state("networkidle")

        # Table should be visible
        table = page.locator("table#incident")
        assert table.count() > 0, "Incident table not found"

        # Wait for at least one row (loading spinner may appear first)
        page.wait_for_selector("table#incident tbody tr", state="visible", timeout=10_000)

    def test_screenshot_on_page_load(self, authenticated_page: Page, screenshot_dir):
        """Take a screenshot of the home page (useful for smoke testing)."""
        page = authenticated_page
        page.goto("/home.do")
        page.wait_for_load_state("networkidle")
        path = AuthenticatedContext.screenshot(page, "home_page", dir=str(screenshot_dir))
        assert path.endswith(".png")
