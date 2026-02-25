"""
Configuration for NotebookLM Skill
Centralizes constants, selectors, and paths
"""

from pathlib import Path

# Paths
SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
BROWSER_STATE_DIR = DATA_DIR / "browser_state"
BROWSER_PROFILE_DIR = BROWSER_STATE_DIR / "browser_profile"
STATE_FILE = BROWSER_STATE_DIR / "state.json"
AUTH_INFO_FILE = DATA_DIR / "auth_info.json"
LIBRARY_FILE = DATA_DIR / "library.json"

# NotebookLM Selectors
QUERY_INPUT_SELECTORS = [
    "textarea.query-box-input",  # Primary
    'textarea[aria-label="Feld für Anfragen"]',  # Fallback German
    'textarea[aria-label="Input for queries"]',  # Fallback English
]

RESPONSE_SELECTORS = [
    ".to-user-container .message-text-content",  # Primary
    "[data-message-author='bot']",
    "[data-message-author='assistant']",
]

# Browser Configuration
BROWSER_ARGS = [
    '--disable-blink-features=AutomationControlled',  # Patches navigator.webdriver
    '--disable-dev-shm-usage',
    '--no-sandbox',
    '--no-first-run',
    '--no-default-browser-check'
]

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

# Timeouts
LOGIN_TIMEOUT_MINUTES = 10
QUERY_TIMEOUT_SECONDS = 120
PAGE_LOAD_TIMEOUT = 30000

# ── Deep Research Configuration ──────────────────────────────────
DEEP_RESEARCH_TIMEOUT_SECONDS = 600   # 10 minutes max
DEEP_RESEARCH_POLL_INTERVAL = 10      # Check every 10 seconds

# Sources panel search input (top of Sources sidebar)
DEEP_RESEARCH_INPUT_SELECTORS = [
    'input[placeholder*="Search the web"]',          # Primary — visible in screenshot
    'input[placeholder*="search" i]',                # Fallback
    'textarea[placeholder*="Search the web"]',       # Textarea variant
    '[aria-label*="search" i][aria-label*="source" i]',
]

# Mode dropdown ("Fast research" → click to switch to "Deep research")
DEEP_RESEARCH_MODE_SELECTORS = [
    'button:has-text("Fast research")',              # Default state
    'button:has-text("Deep research")',              # Already switched
    '[aria-label*="research mode" i]',
    '[aria-label*="research type" i]',
]

# Menu item inside the dropdown to select Deep Research
DEEP_RESEARCH_MENU_ITEM_SELECTORS = [
    'text="Deep research"',                          # Menu option text
    '[role="option"]:has-text("Deep research")',
    '[role="menuitem"]:has-text("Deep research")',
    'li:has-text("Deep research")',
    'div:has-text("Deep research")',
]

# Submit button (arrow "→" next to the search bar)
DEEP_RESEARCH_SUBMIT_SELECTORS = [
    'button[aria-label*="submit" i]',
    'button[aria-label*="search" i]',
    'button[aria-label*="send" i]',
    'button[type="submit"]',
]

# Source type dropdown ("Web" — keep as default)
DEEP_RESEARCH_SOURCE_TYPE_SELECTORS = [
    'button:has-text("Web")',
    '[aria-label*="source type" i]',
]

# Report output — the generated research report
DEEP_RESEARCH_REPORT_SELECTORS = [
    '.research-report',
    '.report-content',
    '[data-report-type]',
    '[role="article"]',
    '.source-card',                                   # Individual source cards
]

# Loading/progress indicators during Deep Research
DEEP_RESEARCH_LOADING_SELECTORS = [
    '[aria-label*="loading" i]',
    '[aria-label*="searching" i]',
    '.progress-indicator',
    '[role="progressbar"]',
]
