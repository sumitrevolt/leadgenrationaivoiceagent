#!/usr/bin/env python3
"""Automate Telegram Web to create 3 missing groups using Selenium.

Opens Chrome -> web.telegram.org -> login -> create groups -> add bot -> get chat_ids.

Usage:
  .venv/Scripts/python.exe scripts/telegram_web_create_groups.py --phone +918459012607
  # After login, provide verification code when prompted
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Force UTF-8 on Windows console
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

GROUPS = [
    {
        "name": "LeadGen AI - Worker Coordination",
        "spec_key": "workers_coordination",
    },
    {
        "name": "LeadGen AI - Agents Coordination",
        "spec_key": "agents_coordination",
    },
    {
        "name": "LeadGen AI - Admin Command Center",
        "spec_key": "admin_command_center",
    },
]

BOT_USERNAME = "Leadsgenai1_bot"


def create_driver():
    """Create Chrome WebDriver with Telegram Web."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    options.binary_location = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    # Use a separate profile to avoid conflicts with user's browsing
    user_data_dir = str(REPO_ROOT / "data" / "telegram_web_profile")
    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-extensions")
    options.add_argument("--window-size=1200,800")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def wait_for_element(driver, css_selector, timeout=30):
    """Wait for element to appear."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
    )


def wait_and_click(driver, css_selector, timeout=30):
    """Wait for element then click."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    el = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, css_selector))
    )
    el.click()
    return el


def type_text(driver, css_selector, text, timeout=30):
    """Type text into an input field."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    el = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
    )
    el.clear()
    el.send_keys(text)
    time.sleep(0.5)
    return el


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone", type=str, required=True, help="Phone number with country code")
    args = parser.parse_args()

    print("[INFO] Starting Chrome with Telegram Web...")
    driver = create_driver()

    try:
        print("[INFO] Navigating to web.telegram.org...")
        driver.get("https://web.telegram.org/a/")
        time.sleep(3)

        # Check if already logged in
        page_source = driver.page_source
        if "log-in" in page_source.lower() or "phone" in page_source.lower():
            print("[INFO] Not logged in. Starting login flow...")

            # Click on "Log In by Phone Number" or similar
            try:
                # Try to find and click phone login option
                time.sleep(2)
                # Telegram Web A uses various selectors
                from selenium.webdriver.common.by import By

                # Try to find the phone input or login button
                elements = driver.find_elements(By.CSS_SELECTOR, "input[type='tel'], input[name='phone'], .btn-primary, .login-btn, a[href*='login']")
                print(f"[INFO] Found {len(elements)} potential login elements")

                # Try direct URL for phone login
                driver.get("https://web.telegram.org/a/#/login")
                time.sleep(3)

                # Take screenshot for debugging
                screenshot_path = str(REPO_ROOT / "data" / "telegram_web_login.png")
                driver.save_screenshot(screenshot_path)
                print(f"[INFO] Screenshot saved: {screenshot_path}")

                # Print page title and URL
                print(f"[INFO] Page title: {driver.title}")
                print(f"[INFO] Current URL: {driver.current_url}")

            except Exception as e:
                print(f"[WARN] Login flow issue: {e}")
                screenshot_path = str(REPO_ROOT / "data" / "telegram_web_debug.png")
                driver.save_screenshot(screenshot_path)
                print(f"[INFO] Debug screenshot: {screenshot_path}")
        else:
            print("[INFO] Already logged in!")

        # Keep browser open for manual inspection
        print("\n[INFO] Browser is open. Check the window.")
        print("[INFO] If you need to scan QR code or enter phone number, do it in the browser window.")
        input("\n[WAIT] Press Enter here after you're logged into Telegram Web...")

        # Now create groups
        print("\n[INFO] Creating groups...")
        results = {}

        for g in GROUPS:
            print(f"\n--- Creating: {g['name']} ---")
            try:
                # Click hamburger menu
                wait_and_click(driver, ".btn-menu, .burger, .header-btn, .sidebar-menu-btn", timeout=10)
                time.sleep(1)

                # Click "New Group"
                from selenium.webdriver.common.by import By
                new_group = driver.find_elements(By.XPATH, "//*[contains(text(), 'New Group') or contains(text(), 'new group')]")
                if new_group:
                    new_group[0].click()
                    time.sleep(1)
                else:
                    print(f"  [FAIL] Could not find 'New Group' option")
                    results[g["spec_key"]] = "FAILED: no_new_group_option"
                    continue

                # Type group name
                name_input = driver.find_elements(By.CSS_SELECTOR, "input[placeholder*='group'], input[placeholder*='name'], input[type='text']")
                if name_input:
                    name_input[0].clear()
                    name_input[0].send_keys(g["name"])
                    time.sleep(0.5)
                else:
                    print(f"  [FAIL] Could not find name input")
                    results[g["spec_key"]] = "FAILED: no_name_input"
                    continue

                # Click Next/Create
                next_btn = driver.find_elements(By.XPATH, "//button[contains(text(), 'Next') or contains(text(), 'Create') or contains(@class, 'primary')]")
                if next_btn:
                    next_btn[0].click()
                    time.sleep(2)

                # Add bot
                search_input = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[placeholder*='search'], input[placeholder*='member']")
                if search_input:
                    search_input[0].send_keys(BOT_USERNAME)
                    time.sleep(2)

                    # Click on bot in results
                    bot_result = driver.find_elements(By.XPATH, f"//*[contains(text(), '{BOT_USERNAME}')]")
                    if bot_result:
                        bot_result[0].click()
                        time.sleep(0.5)

                # Click Create/Join
                create_btn = driver.find_elements(By.XPATH, "//button[contains(text(), 'Create') or contains(text(), 'Join')]")
                if create_btn:
                    create_btn[0].click()
                    time.sleep(3)

                # Get chat link
                time.sleep(2)
                screenshot_path = str(REPO_ROOT / "data" / f"telegram_group_{g['spec_key']}.png")
                driver.save_screenshot(screenshot_path)

                # Try to get invite link
                current_url = driver.current_url
                results[g["spec_key"]] = current_url
                print(f"  [OK] Group created. URL: {current_url}")
                print(f"  [INFO] Screenshot: {screenshot_path}")

            except Exception as e:
                print(f"  [FAIL] Error: {e}")
                results[g["spec_key"]] = f"FAILED: {e}"
                screenshot_path = str(REPO_ROOT / "data" / f"telegram_error_{g['spec_key']}.png")
                driver.save_screenshot(screenshot_path)

        # Output results
        print("\n" + "=" * 60)
        print("RESULTS:")
        print("=" * 60)
        for spec_key, url in results.items():
            print(f"  {spec_key}: {url}")

        results_path = REPO_ROOT / "data" / "new_group_chat_ids.json"
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nSaved to: {results_path}")

    except Exception as e:
        print(f"[FATAL] {e}")
        screenshot_path = str(REPO_ROOT / "data" / "telegram_web_fatal.png")
        try:
            driver.save_screenshot(screenshot_path)
            print(f"[INFO] Screenshot: {screenshot_path}")
        except Exception:
            pass
    finally:
        print("\n[INFO] Browser kept open for inspection. Close manually when done.")
        input("[WAIT] Press Enter to close browser...")
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
