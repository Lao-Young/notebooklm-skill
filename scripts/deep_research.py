#!/usr/bin/env python3
"""
Deep Research automation for NotebookLM
Triggers Deep Research in the Sources panel, waits for completion,
and captures the generated report.

Usage:
    python scripts/run.py deep_research.py --topic "..." --notebook-url "..."
    python scripts/run.py deep_research.py --discover --notebook-url "..."
"""

import argparse
import sys
import time
import re
from pathlib import Path

from patchright.sync_api import sync_playwright

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from notebook_manager import NotebookLibrary
from config import (
    DEEP_RESEARCH_INPUT_SELECTORS,
    DEEP_RESEARCH_MODE_SELECTORS,
    DEEP_RESEARCH_MENU_ITEM_SELECTORS,
    DEEP_RESEARCH_SUBMIT_SELECTORS,
    DEEP_RESEARCH_REPORT_SELECTORS,
    DEEP_RESEARCH_LOADING_SELECTORS,
    DEEP_RESEARCH_TIMEOUT_SECONDS,
    DEEP_RESEARCH_POLL_INTERVAL,
)
from browser_utils import BrowserFactory, StealthUtils


def find_element(page, selectors, description, timeout=10000):
    """Try multiple selectors to find an element. Returns (element, selector) or (None, None)."""
    for selector in selectors:
        try:
            element = page.wait_for_selector(selector, timeout=timeout, state="visible")
            if element:
                print(f"  [OK] Found {description}: {selector}")
                return element, selector
        except Exception:
            continue
    return None, None


def find_element_quick(page, selectors, description):
    """Quick check without waiting — for elements that should already be visible."""
    for selector in selectors:
        try:
            element = page.query_selector(selector)
            if element and element.is_visible():
                print(f"  [OK] Found {description}: {selector}")
                return element, selector
        except Exception:
            continue
    return None, None


def discover_ui(notebook_url):
    """
    Discovery mode: open notebook visible, dump all interactive elements.
    One-time use to find the right selectors.
    """
    auth = AuthManager()
    if not auth.is_authenticated():
        print("[!] Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return

    print("=== Deep Research UI Discovery Mode ===")
    print(f"Notebook: {notebook_url}")
    print("Opening notebook in visible browser...")

    playwright = None
    context = None

    try:
        playwright = sync_playwright().start()
        context = BrowserFactory.launch_persistent_context(playwright, headless=False)
        page = context.new_page()

        page.goto(notebook_url, wait_until="domcontentloaded")
        page.wait_for_url(re.compile(r"^https://notebooklm\.google\.com/"), timeout=15000)

        # Wait for page to fully load
        print("Waiting for page to load...")
        time.sleep(5)

        # Dump all buttons
        print("\n--- ALL BUTTONS ---")
        buttons = page.query_selector_all("button")
        for i, btn in enumerate(buttons):
            try:
                text = btn.inner_text().strip()[:80]
                aria = btn.get_attribute("aria-label") or ""
                classes = btn.get_attribute("class") or ""
                visible = btn.is_visible()
                print(f"  [{i}] text='{text}' | aria='{aria}' | class='{classes[:60]}' | visible={visible}")
            except Exception:
                pass

        # Dump all inputs
        print("\n--- ALL INPUTS ---")
        inputs = page.query_selector_all("input, textarea")
        for i, inp in enumerate(inputs):
            try:
                placeholder = inp.get_attribute("placeholder") or ""
                aria = inp.get_attribute("aria-label") or ""
                inp_type = inp.get_attribute("type") or ""
                tag = inp.evaluate("el => el.tagName")
                visible = inp.is_visible()
                print(f"  [{i}] <{tag}> type='{inp_type}' | placeholder='{placeholder}' | aria='{aria}' | visible={visible}")
            except Exception:
                pass

        # Dump dropdowns / selects
        print("\n--- ALL SELECTS / DROPDOWNS ---")
        selects = page.query_selector_all("select, [role='listbox'], [role='combobox'], [role='menu']")
        for i, sel in enumerate(selects):
            try:
                tag = sel.evaluate("el => el.tagName")
                aria = sel.get_attribute("aria-label") or ""
                role = sel.get_attribute("role") or ""
                text = sel.inner_text().strip()[:80]
                print(f"  [{i}] <{tag}> role='{role}' | aria='{aria}' | text='{text}'")
            except Exception:
                pass

        # Try our configured selectors
        print("\n--- SELECTOR TESTS ---")
        for name, selectors in [
            ("Search input", DEEP_RESEARCH_INPUT_SELECTORS),
            ("Mode dropdown", DEEP_RESEARCH_MODE_SELECTORS),
            ("Submit button", DEEP_RESEARCH_SUBMIT_SELECTORS),
        ]:
            elem, sel = find_element_quick(page, selectors, name)
            if not elem:
                print(f"  [MISS] {name}: None of the configured selectors matched")

        print("\n=== Discovery complete. Browser stays open for manual inspection. ===")
        print("Press Ctrl+C to close.")

        # Keep browser open for manual inspection
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nClosing browser...")

    except Exception as e:
        print(f"[!] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if context:
            try:
                context.close()
            except Exception:
                pass
        if playwright:
            try:
                playwright.stop()
            except Exception:
                pass


def run_deep_research(topic, notebook_url, mode="deep", timeout=None):
    """
    Run Deep Research on a NotebookLM notebook.

    Flow (based on live UI inspection):
    1. Open notebook URL
    2. Click "+ Add sources" to open the sources modal
    3. In the modal: find search input "Search the web for new sources"
    4. Switch "Fast research" dropdown → "Deep research"
    5. Type topic, click submit arrow →
    6. Wait for completion (up to 10 min)
    7. Capture report

    Args:
        topic: Research topic/question
        notebook_url: NotebookLM notebook URL
        mode: "deep" or "fast" (default: "deep")
        timeout: Max wait time in seconds (default: from config)

    Returns:
        dict with keys: success, sources_count, report (or error)
    """
    if timeout is None:
        timeout = DEEP_RESEARCH_TIMEOUT_SECONDS

    auth = AuthManager()
    if not auth.is_authenticated():
        print("[!] Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return {"success": False, "error": "Not authenticated"}

    print(f"{'='*60}")
    print(f"Deep Research: {topic}")
    print(f"Notebook: {notebook_url}")
    print(f"Mode: {mode} | Timeout: {timeout}s")
    print(f"{'='*60}")

    playwright = None
    context = None

    try:
        playwright = sync_playwright().start()

        # Always visible — Deep Research takes minutes, user can monitor
        context = BrowserFactory.launch_persistent_context(playwright, headless=False)
        page = context.new_page()

        # Maximize window for reliable element detection
        page.set_viewport_size({"width": 1920, "height": 1080})

        # ── Step 1: Open notebook ──
        print("\n[1/7] Opening notebook...")
        page.goto(notebook_url, wait_until="domcontentloaded")
        page.wait_for_url(re.compile(r"^https://notebooklm\.google\.com/"), timeout=15000)

        # Wait for page to be interactive
        time.sleep(4)
        StealthUtils.random_delay(1000, 2000)

        # ── Step 2: Click "+ Add sources" to open modal ──
        print("\n[2/7] Opening Add Sources modal...")
        add_sources_selectors = [
            'button:has-text("Add sources")',
            'button:has-text("+ Add sources")',
            '[aria-label*="Add sources" i]',
            'button:has-text("Add source")',
        ]
        add_btn, _ = find_element(page, add_sources_selectors, "Add sources button", timeout=10000)

        if not add_btn:
            # The search bar might already be visible (new notebook or panel open)
            print("  '+ Add sources' not found, checking if search bar already visible...")
        else:
            add_btn.click()
            StealthUtils.random_delay(1000, 2000)
            print("  [OK] Modal opened")

        # ── Step 3: Find the search input in the modal ──
        print("\n[3/7] Finding search input in modal...")

        # The modal has its own search bar with same placeholder
        # Try to find it — prefer the one inside a dialog/modal
        search_input = None
        search_sel = None

        # First: try to find search input inside a modal/dialog
        modal_search_selectors = [
            'dialog input[placeholder*="Search the web"]',
            '[role="dialog"] input[placeholder*="Search the web"]',
            '.modal input[placeholder*="Search the web"]',
            '[class*="modal"] input[placeholder*="Search the web"]',
            '[class*="dialog"] input[placeholder*="Search the web"]',
        ]
        search_input, search_sel = find_element(page, modal_search_selectors, "modal search input", timeout=5000)

        # Fallback: try all configured selectors (might match sidebar or modal)
        if not search_input:
            search_input, search_sel = find_element(page, DEEP_RESEARCH_INPUT_SELECTORS, "search input", timeout=10000)

        # Last resort: scan all visible inputs for "search" placeholder
        if not search_input:
            print("  Fallback: scanning all visible inputs...")
            for inp in page.query_selector_all("input, textarea"):
                try:
                    if inp.is_visible():
                        placeholder = inp.get_attribute("placeholder") or ""
                        if "search" in placeholder.lower() and "web" in placeholder.lower():
                            search_input = inp
                            search_sel = f'input[placeholder="{placeholder}"]'
                            print(f"  [OK] Fallback found: placeholder='{placeholder}'")
                            break
                except Exception:
                    continue

        if not search_input:
            return {"success": False, "error": "Could not find search input in Sources modal"}

        # ── Step 4: Switch mode from Fast to Deep ──
        print(f"\n[4/7] Switching to {mode} research mode...")

        if mode == "deep":
            # Find the mode dropdown (should say "Fast research" by default)
            # Look for it near the search input (inside the modal context)
            mode_btn = None

            # Try text-based matching first
            mode_selectors = [
                'button:has-text("Fast research")',
                'button:has-text("Deep research")',
            ]
            mode_btn, mode_sel = find_element_quick(page, mode_selectors, "mode dropdown")

            # If there are multiple (sidebar + modal), prefer the second one (modal)
            if mode_btn:
                all_mode_btns = page.query_selector_all('button:has-text("Fast research")')
                if len(all_mode_btns) > 1:
                    # Use the last one (modal is rendered after sidebar)
                    mode_btn = all_mode_btns[-1]
                    print(f"  Multiple mode buttons found ({len(all_mode_btns)}), using modal one")

            if mode_btn:
                mode_text = mode_btn.inner_text().strip().lower()
                if "fast" in mode_text:
                    print("  Clicking mode dropdown to switch to Deep...")
                    mode_btn.click()
                    StealthUtils.random_delay(500, 1000)

                    # Find and click "Deep research" in the dropdown menu
                    deep_item, _ = find_element(page, DEEP_RESEARCH_MENU_ITEM_SELECTORS, "Deep research option", timeout=5000)
                    if deep_item:
                        deep_item.click()
                        StealthUtils.random_delay(300, 600)
                        print("  [OK] Switched to Deep research mode")
                    else:
                        # Try clicking by locator text
                        print("  Trying locator-based click...")
                        try:
                            page.locator("text=Deep research").last.click()
                            StealthUtils.random_delay(300, 600)
                            print("  [OK] Switched via locator")
                        except Exception:
                            print("  [WARN] Could not switch to Deep mode, continuing with Fast")
                elif "deep" in mode_text:
                    print("  Already in Deep research mode")
            else:
                print("  [WARN] Mode dropdown not found, will try with current mode")

        # ── Step 5: Type the research topic ──
        print(f"\n[5/7] Entering topic: {topic[:60]}...")
        search_input.click()
        StealthUtils.random_delay(200, 500)

        # Clear any existing text first
        page.keyboard.press("Control+a")
        page.keyboard.press("Backspace")
        StealthUtils.random_delay(100, 300)

        # Type topic with human-like speed
        StealthUtils.human_type(page, search_sel, topic)
        StealthUtils.random_delay(500, 1000)

        # ── Step 6: Submit ──
        print("\n[6/7] Submitting research request...")

        # Try submit button (arrow →) — prefer the one in the modal
        submit_btn = None
        submit_selectors = DEEP_RESEARCH_SUBMIT_SELECTORS + [
            'button[aria-label*="arrow" i]',
            'button:has-text("→")',
        ]

        for sel in submit_selectors:
            try:
                btns = page.query_selector_all(sel)
                for btn in btns:
                    if btn.is_visible():
                        submit_btn = btn
                        print(f"  [OK] Found submit: {sel}")
                        break
                if submit_btn:
                    break
            except Exception:
                continue

        if submit_btn:
            submit_btn.click()
        else:
            # Fallback: press Enter
            print("  Submit button not found, pressing Enter...")
            page.keyboard.press("Enter")

        StealthUtils.random_delay(2000, 3000)
        print("  [OK] Request submitted!")

        # ── Step 7: Wait for completion ──
        print(f"\n[7/7] Waiting for research to complete (up to {timeout}s)...")
        print("  You can watch progress in the browser window.")

        start_time = time.time()
        deadline = start_time + timeout
        initial_source_count = len(page.query_selector_all('.source-card, [data-source-id], .source-item, [class*="source-list"] > *'))
        last_sources_count = initial_source_count
        stable_count = 0
        last_status = ""
        check_num = 0

        while time.time() < deadline:
            check_num += 1
            elapsed = int(time.time() - start_time)
            remaining = int(deadline - time.time())

            # ── Check for new sources appearing in the sidebar ──
            try:
                source_elements = page.query_selector_all(
                    '.source-card, [data-source-id], .source-item, '
                    '[class*="source-list"] > *, [class*="source_list"] > *'
                )
                current_count = len(source_elements)

                if current_count != last_sources_count:
                    new_count = current_count - initial_source_count
                    print(f"  [{elapsed}s] Sources: {current_count} total (+{new_count} new)")
                    last_sources_count = current_count
                    stable_count = 0
                else:
                    stable_count += 1
            except Exception:
                pass

            # ── Check for loading/progress indicators ──
            is_loading = False
            for sel in DEEP_RESEARCH_LOADING_SELECTORS:
                try:
                    loader = page.query_selector(sel)
                    if loader and loader.is_visible():
                        is_loading = True
                        break
                except Exception:
                    continue

            # Also check for spinners, progress bars, animations
            if not is_loading:
                try:
                    spinners = page.query_selector_all(
                        '[class*="spinner"], [class*="loading"], [class*="progress"], '
                        '[class*="searching"], [class*="animat"]'
                    )
                    for s in spinners:
                        if s.is_visible():
                            is_loading = True
                            break
                except Exception:
                    pass

            # ── Check for "Deep Research report" appearing as a source ──
            try:
                report_sources = page.query_selector_all(
                    '[class*="source"]:has-text("Deep Research report"), '
                    '[class*="source"]:has-text("deep research")'
                )
                if report_sources:
                    for rs in report_sources:
                        if rs.is_visible():
                            print(f"  [{elapsed}s] Deep Research report appeared as source!")
                            is_loading = False
                            stable_count = 10  # Force completion
                            break
            except Exception:
                pass

            # ── Status update every 30 seconds ──
            if check_num % 3 == 0:
                status = f"loading={is_loading}, sources={last_sources_count}, stable={stable_count}"
                if status != last_status:
                    print(f"  [{elapsed}s] {status} | {remaining}s left")
                    last_status = status

            # ── Completion: stable for 5 polls with new sources and no loading ──
            new_sources = last_sources_count - initial_source_count
            if stable_count >= 5 and not is_loading and new_sources > 0:
                print(f"  [{elapsed}s] Research complete! ({new_sources} new sources, stable)")
                break

            # Also complete if we've been stable for a long time (even with 0 new sources)
            # This handles the case where research finishes but source count doesn't change visibly
            if stable_count >= 12 and not is_loading and elapsed > 60:
                print(f"  [{elapsed}s] Research appears complete (stable for {stable_count * DEEP_RESEARCH_POLL_INTERVAL}s)")
                break

            time.sleep(DEEP_RESEARCH_POLL_INTERVAL)

        total_elapsed = int(time.time() - start_time)
        new_sources = last_sources_count - initial_source_count

        # ── Capture results ──
        print(f"\nCapturing results... ({total_elapsed}s elapsed, {new_sources} new sources)")

        # Strategy 1: Look for the Deep Research report in the chat/main area
        report_text = None

        # The report might appear as a source that can be clicked, or in the chat
        # Try chat area first (where Q&A responses appear)
        chat_selectors = [
            ".to-user-container .message-text-content",
            "[data-message-author='bot']",
            "[data-message-author='assistant']",
            '[class*="response"]',
            '[class*="answer"]',
        ]
        for sel in chat_selectors:
            try:
                elements = page.query_selector_all(sel)
                if elements:
                    # Get the latest/largest response
                    texts = []
                    for el in elements:
                        if el.is_visible():
                            text = el.inner_text().strip()
                            if len(text) > 100:
                                texts.append(text)
                    if texts:
                        report_text = max(texts, key=len)  # Take the longest
                        print(f"  [OK] Captured from chat: {sel} ({len(report_text)} chars)")
                        break
            except Exception:
                continue

        # Strategy 2: Try Deep Research specific report selectors
        if not report_text:
            for sel in DEEP_RESEARCH_REPORT_SELECTORS:
                try:
                    elements = page.query_selector_all(sel)
                    if elements:
                        texts = [el.inner_text().strip() for el in elements if el.is_visible() and len(el.inner_text().strip()) > 50]
                        if texts:
                            report_text = "\n\n".join(texts)
                            print(f"  [OK] Captured from: {sel} ({len(texts)} elements)")
                            break
                except Exception:
                    continue

        # Strategy 3: Try to click the "Deep Research report" source to view it
        if not report_text:
            print("  Trying to click Deep Research report source...")
            try:
                report_link = page.locator('text=/Deep Research report/i').first
                if report_link:
                    report_link.click()
                    StealthUtils.random_delay(2000, 3000)

                    # Now try to read the opened report
                    for sel in ['[class*="report"]', '[class*="content"]', '[role="article"]', 'main', '.content']:
                        try:
                            el = page.query_selector(sel)
                            if el and el.is_visible():
                                text = el.inner_text().strip()
                                if len(text) > 200:
                                    report_text = text
                                    print(f"  [OK] Captured opened report: {sel} ({len(text)} chars)")
                                    break
                        except Exception:
                            continue
            except Exception:
                pass

        # Strategy 4: Capture sources list as summary
        if not report_text:
            print("  Capturing sources list as summary...")
            try:
                sources_panel = page.query_selector('[class*="source"]')
                if sources_panel:
                    report_text = sources_panel.inner_text().strip()
                    if len(report_text) > 50:
                        print(f"  [OK] Sources panel text ({len(report_text)} chars)")
            except Exception:
                pass

        # Strategy 5: Full page text
        if not report_text:
            print("  Last resort: full page text...")
            try:
                report_text = page.inner_text("body")
                print(f"  [OK] Full page ({len(report_text)} chars)")
            except Exception:
                pass

        if not report_text:
            return {
                "success": False,
                "error": "Could not capture research results",
                "sources_count": new_sources,
                "elapsed_seconds": total_elapsed,
            }

        return {
            "success": True,
            "sources_count": new_sources,
            "total_sources": last_sources_count,
            "elapsed_seconds": total_elapsed,
            "report": report_text,
        }

    except Exception as e:
        print(f"\n[!] Error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

    finally:
        if context:
            try:
                context.close()
            except Exception:
                pass
        if playwright:
            try:
                playwright.stop()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="NotebookLM Deep Research")

    parser.add_argument("--topic", help="Research topic/question")
    parser.add_argument("--notebook-url", help="NotebookLM notebook URL")
    parser.add_argument("--notebook-id", help="Notebook ID from library")
    parser.add_argument("--mode", choices=["deep", "fast"], default="deep",
                        help="Research mode (default: deep)")
    parser.add_argument("--timeout", type=int, default=DEEP_RESEARCH_TIMEOUT_SECONDS,
                        help=f"Max wait time in seconds (default: {DEEP_RESEARCH_TIMEOUT_SECONDS})")
    parser.add_argument("--discover", action="store_true",
                        help="Discovery mode: dump UI elements for selector tuning")

    args = parser.parse_args()

    # Resolve notebook URL
    notebook_url = args.notebook_url
    if not notebook_url and args.notebook_id:
        library = NotebookLibrary()
        notebook = library.get_notebook(args.notebook_id)
        if notebook:
            notebook_url = notebook["url"]
        else:
            print(f"[!] Notebook '{args.notebook_id}' not found in library")
            return 1

    if not notebook_url:
        # Try active notebook
        library = NotebookLibrary()
        active = library.get_active_notebook()
        if active:
            notebook_url = active["url"]
            print(f"Using active notebook: {active['name']}")
        else:
            print("[!] No notebook URL provided. Use --notebook-url or --notebook-id")
            return 1

    # Discovery mode
    if args.discover:
        discover_ui(notebook_url)
        return 0

    # Run Deep Research
    if not args.topic:
        print("[!] --topic is required for research mode")
        return 1

    result = run_deep_research(
        topic=args.topic,
        notebook_url=notebook_url,
        mode=args.mode,
        timeout=args.timeout,
    )

    if result["success"]:
        print(f"\n{'='*60}")
        print(f"Deep Research Complete!")
        print(f"Sources found: {result.get('sources_count', 'unknown')}")
        print(f"{'='*60}")
        print()
        print(result["report"])
        print()
        print(f"{'='*60}")
        return 0
    else:
        print(f"\n[!] Deep Research failed: {result.get('error', 'Unknown error')}")
        if result.get("sources_count"):
            print(f"  Sources found before failure: {result['sources_count']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
