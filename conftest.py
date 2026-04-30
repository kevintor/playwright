"""
pytest configuration and shared fixtures for ServiceNow Playbook GUI tests.
"""

import os
import pytest
from pathlib import Path


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "playbook: mark test as a Playbook E2E test")
    config.addinivalue_line("markers", "gui: mark test as a GUI/browser test")
    config.addinivalue_line("markers", "slow: mark test as slow running")


def pytest_addoption(parser):
    """Add custom CLI options."""
    parser.addoption(
        "--instance",
        action="store",
        default=os.environ.get("SN_INSTANCE", ""),
        help="ServiceNow instance URL (or set SN_INSTANCE env var)",
    )
    parser.addoption(
        "--username",
        action="store",
        default=os.environ.get("SN_USER", ""),
        help="ServiceNow username (or set SN_USER env var)",
    )
    parser.addoption(
        "--password",
        action="store",
        default=os.environ.get("SN_PASS", ""),
        help="ServiceNow password (or set SN_PASS env var)",
    )
    parser.addoption(
        "--mfa-token",
        action="store",
        default=os.environ.get("SN_MFA_TOKEN", ""),
        help="MFA/OTP token if MFA is enabled (or set SN_MFA_TOKEN env var)",
    )
    parser.addoption(
        "--browser",
        action="store",
        default=os.environ.get("BROWSER_TYPE", "chromium"),
        choices=["chromium", "firefox", "webkit"],
        help="Browser to use (default: chromium)",
    )
    parser.addoption(
        "--no-headless",
        action="store_true",
        default=False,
        help="Run browser in headed mode (visible window)",
    )
    parser.addoption(
        "--slow-mo",
        action="store",
        type=int,
        default=int(os.environ.get("SLOW_MO", "0")),
        help="Slow Playwright actions by N ms (for debugging)",
    )
    parser.addoption(
        "--screenshots",
        action="store",
        default=os.environ.get("SCREENSHOT_DIR", "screenshots"),
        help="Directory to save screenshots",
    )
    parser.addoption(
        "--stage-timeout",
        action="store",
        type=int,
        default=180,
        help="Default timeout in seconds for stage polling",
    )


@pytest.fixture(scope="session")
def screenshot_dir(request) -> Path:
    """Create and return screenshots directory."""
    d = Path(request.config.getoption("--screenshots"))
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture(scope="session")
def stage_timeout(request) -> int:
    """Default stage polling timeout in seconds."""
    return request.config.getoption("--stage-timeout")


# ── HTML report hook ────────────────────────────────────────────────────────
# Adds screenshot links to the pytest-html report.

def pytest_html_report_title(report):
    report.title = "ServiceNow Playbook GUI Test Report"


def pytest_html_report_extra(report, meta):
    """Embed screenshots in the HTML report if present."""
    screenshot_path = meta.get("screenshot", None)
    if screenshot_path and Path(screenshot_path).exists():
        report.extra.append(
            ("<img src='{}' width='800'/>".format(screenshot_path), "", "")
        )
