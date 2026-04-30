# ServiceNow Playbook GUI Testing — Playwright

**Python + Playwright E2E browser automation for ServiceNow Playbook workflows.**

This project provides a complete test framework for GUI-testing ServiceNow Playbooks using [Playwright](https://playwright.dev/python/) and pytest. It logs in via browser (supporting standard auth, MFA/OTP, and okta/SSO), triggers Playbook workflows, polls stage transitions from the DOM, and captures screenshots on every assertion for rich CI/CD reports.

---

## Project Structure

```
playwright/                       ← GitHub repo root
├── servicenow_client.py         # Core Playwright client & fixtures
├── conftest.py                  # pytest config, CLI options, HTML report hooks
├── requirements.txt             # Python dependencies
├── README.md                    # This file
├── .env.example                 # Environment variable template
├── .gitignore
└── tests/
    ├── __init__.py
    ├── test_playbook_e2e.py     # E2E Playbook tests
    └── .github/
        └── workflows/
            └── tests.yml        # GitHub Actions CI/CD workflow
```

---

## Features

| Feature | Detail |
|---------|--------|
| **Browser login** | Standard ServiceNow, MFA (Duo/TOTP), okta SSO |
| **Playbook stage polling** | Watches `.workflow-stage-label` DOM element until target stage is reached |
| **Screenshot on every step** | PNG screenshot saved on each assertion for debugging |
| **HTML report** | pytest-html generates a self-contained report with screenshots embedded |
| **Config via env vars** | Zero hardcoded credentials; works with GitHub Secrets |
| **CI/CD ready** | GitHub Actions workflow included |
| **Multi-browser** | Chromium, Firefox, WebKit — switch via env var |
| **Headless / Headed** | Toggle via CLI flag or `HEADLESS=false` |

---

## Prerequisites

- Python **3.11+**
- [Node.js & npm](https://nodejs.org/) — required to install Playwright browsers
- A ServiceNow **developer instance** (or any non-production instance)
- Git

---

## Installation

### 1. Clone / create the project directory

```bash
# If starting fresh:
git init playwright
cd playwright
mkdir -p tests .github/workflows
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
# .\.venv\Scripts\Activate     # Windows
```

### 3. Install Python dependencies

```bash
pip install --upgrade pip
pip install playwright pytest pytest-html
```

### 4. Install Playwright browsers

```bash
# Downloads ~100 MB Chromium (with dependencies)
playwright install --with-deps chromium
```

> To use Firefox or WebKit instead:
> ```bash
> playwright install --with-deps firefox
> # or
> playwright install --with-deps webkit
> ```

### 5. Copy and fill in environment variables

```bash
cp .env.example .env
```

Edit `.env` (or set the variables directly in your shell):

```bash
# Required
export SN_INSTANCE="https://dev12345.service-now.com"
export SN_USER="admin"
export SN_PASS="your-password"

# Optional — required only if MFA is enabled on your account
export SN_MFA_TOKEN="123456"
```

### 6. Verify Playwright installation

```bash
python -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
```

---

## Usage

### Run all tests

```bash
pytest tests/ --html=report.html --self-contained-html -v
```

### Run a specific test

```bash
pytest tests/test_playbook_e2e.py::TestIncidentPlaybook::test_playbook_reaches_containment_stage \
  --html=report.html --self-contained-html -v
```

### Run in headed (visible) browser

```bash
HEADLESS=false pytest tests/ -v
```

### Custom stage timeout

```bash
pytest tests/ --stage-timeout=300   # 5 minutes
```

### With CLI options (no env vars)

```bash
pytest tests/ \
  --instance="https://dev12345.service-now.com" \
  --username="admin" \
  --password="secret" \
  --browser="chromium" \
  --html=report.html --self-contained-html -v
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SN_INSTANCE` | **Yes** | — | ServiceNow instance URL, e.g. `https://dev12345.service-now.com` |
| `SN_USER` | **Yes** | — | Username |
| `SN_PASS` | **Yes** | — | Password |
| `SN_MFA_TOKEN` | No | — | OTP code for MFA-enabled accounts |
| `SN_TIMEOUT` | No | `30000` | Page load timeout in milliseconds |
| `BROWSER_TYPE` | No | `chromium` | `chromium`, `firefox`, or `webkit` |
| `HEADLESS` | No | `true` | Set to `false` for visible browser |
| `SLOW_MO` | No | `0` | Milliseconds between Playwright actions (debug) |
| `SCREENSHOT_DIR` | No | `screenshots` | Directory for PNG screenshots |

---

## How It Works

### 1. Login (`AuthenticatedContext.login()`)

The framework detects which login flow is in effect:

```
Standard ServiceNow form  → fill user_name + user_password → submit
MFA / Duo / TOTP          → fill otp input → submit
okta / SSO redirect       → follow okta form → submit
```

After login, if ServiceNow loads the app inside a `gsft_main` iframe, the client automatically switches to that frame.

### 2. Playbook Stage Polling

```python
AuthenticatedContext.wait_for_stage(
    page,
    stage_name="Containment",   # matches if "Containment" appears in the label
    timeout=180_000,           # ms
    exact=False,
)
```

Internally it:
- Waits up to `timeout` ms
- Checks every 2 s
- Returns `True` on match; raises `TimeoutError` otherwise

### 3. Screenshot Hook

Every test screenshot is saved to `screenshots/<test_name>_<sys_id>.png`. On failure, the path is embedded in the pytest-html report for instant visual diagnosis.

---

## CI/CD — GitHub Actions

> ⚠️ **Note:** The GitHub Actions workflow (`.github/workflows/tests.yml`) could not be auto-pushed due to token scope restrictions. Copy it manually or add `workflow` scope to your token, then push from a local clone.
>
> **Raw workflow file:** https://raw.githubusercontent.com/kevintor/playwright/main/.github/workflows/tests.yml

### Manual setup (one-time)

```bash
# Clone the repo
git clone https://github.com/kevintor/playwright.git
cd playwright

# Create workflows directory and add the workflow
mkdir -p .github/workflows
# Copy tests.yml content from the URL above, then:
git add .github/workflows/tests.yml
git commit -m "Add GitHub Actions workflow"
git push
```

### Workflow file content (`.github/workflows/tests.yml`)

```yaml
name: ServiceNow Playbook GUI Tests

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]
  workflow_dispatch:

jobs:
  playwright-tests:
    name: Run Playwright E2E Tests
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install playwright pytest pytest-html
          playwright install --with-deps chromium

      - name: Run tests
        env:
          SN_INSTANCE: ${{ secrets.SN_INSTANCE }}
          SN_USER: ${{ secrets.SN_USER }}
          SN_PASS: ${{ secrets.SN_PASS }}
          SN_MFA_TOKEN: ${{ secrets.SN_MFA_TOKEN }}
        run: |
          pytest tests/ --html=report.html --self-contained-html -v

      - name: Upload screenshots on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: failure-screenshots
          path: screenshots/*.png
          retention-days: 7

      - name: Upload HTML report
        uses: actions/upload-artifact@v4
        with:
          name: playwright-html-report
          path: report.html
          retention-days: 14
```

### Secrets required (Settings → Secrets → Actions)

| Secret | Description |
|--------|-------------|
| `SN_INSTANCE` | ServiceNow instance URL |
| `SN_USER` | Username |
| `SN_PASS` | Password |
| `SN_MFA_TOKEN` | OTP (if MFA is enabled) |

### Variables (Settings → Variables → Actions)

| Variable | Default | Description |
|----------|---------|-------------|
| `BROWSER_TYPE` | `chromium` | Browser choice |

### Workflow Triggers

- **Push** to `main`/`master`
- **Pull requests**
- **Manual** (`workflow_dispatch`)

---

## Extending

### Add a new Playbook test

```python
@pytest.mark.playbook
@pytest.mark.gui
def test_my_playbook_stage(self, authenticated_page: Page, stage_timeout: int):
    page = authenticated_page
    sys_id = create_incident_with_playbook(
        page,
        short_description="My Test",
        playbook_name="my_custom_playbook",
    )
    navigate_to_incident(page, sys_id)

    found = AuthenticatedContext.wait_for_stage(
        page, stage_name="My Stage", timeout=stage_timeout * 1000
    )
    assert found
```

### Use Firefox or WebKit

```bash
export BROWSER_TYPE=firefox
pytest tests/
```

### Add a custom DOM selector for your instance

Edit `PlaywrightConfig` in `servicenow_client.py`:

```python
@dataclass
class PlaywrightConfig:
    ...
    stage_label: str = ".my-custom-stage-css"   # override the default
```

---

## Troubleshooting

### `TimeoutError: Stage 'Containment' never appeared`

1. **Playbook not attached** — ensure the `playbook_name` value matches the exact internal name in your ServiceNow instance (check `sys_idsysdictionary` or the Playbook dropdown).
2. **Stage name mismatch** — check the actual text in `.workflow-stage-label` on your instance and use `exact=False` with the correct substring.
3. **Playbook locked** — ServiceNow Studio may lock Playbooks; unlock via `glide.script.studio.playbook.locking.enabled=false`.

### Login fails / "Access denied"

- Verify `SN_INSTANCE` does **not** have a trailing slash.
- If using MFA, ensure `SN_MFA_TOKEN` is set and the OTP hasn't expired.
- For okta/SSO accounts, check that your org's okta URL is reachable from the test environment.

### Browser not launching

```bash
# Reinstall Playwright with system dependencies
playwright install --with-deps
```

### "context or browser has been closed"

This happens when a `BrowserContext` goes out of scope during a test. Ensure you consume the `authenticated_page` fixture inside the test function body and do not close it manually.

---

## License

MIT
