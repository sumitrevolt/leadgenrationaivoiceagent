"""
OmniRoute Live Setup Assistant
Uses Playwright with installed Google Chrome to open OmniRoute dashboard
and provider portals, allowing interactive setup of 14 Combos x 14 Emails x 42 Providers.
"""

import os
import sys
import time

from playwright.sync_api import sync_playwright

OMNIROUTE_URL = "http://127.0.0.1:20128"

PROVIDER_PORTALS = [
    ("Google AI Studio (Gemini)", "https://aistudio.google.com/app/apikey"),
    ("Groq Cloud", "https://console.groq.com/keys"),
    ("Cerebras Cloud", "https://cloud.cerebras.ai/"),
    ("OpenRouter", "https://openrouter.ai/keys"),
    ("SambaNova Cloud", "https://cloud.sambanova.ai/apis"),
    ("Mistral Console", "https://console.mistral.ai/api-keys/"),
    ("GitHub Models", "https://github.com/marketplace/models"),
    ("SiliconFlow", "https://cloud.siliconflow.cn/account/ak"),
]

def main():
    print("=" * 70, flush=True)
    print("  OmniRoute Live Assistant (Chrome + Playwright)", flush=True)
    print("  Setup 14 Combos x 14 Emails x 42 Free Providers", flush=True)
    print("=" * 70, flush=True)

    with sync_playwright() as p:
        print("[1] Launching Google Chrome on your screen...", flush=True)
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--start-maximized"]
        )
        context = browser.new_context(no_viewport=True)

        # Tab 1: OmniRoute Providers
        page_providers = context.new_page()
        print(f"[2] Opening OmniRoute Providers: {OMNIROUTE_URL}/dashboard/providers", flush=True)
        page_providers.goto(f"{OMNIROUTE_URL}/dashboard/providers", wait_until="domcontentloaded")
        page_providers.wait_for_timeout(2000)

        # Open Onboarding Wizard
        try:
            wizard_btn = page_providers.query_selector('button:has-text("Provider Onboarding Wizard")') or \
                         page_providers.query_selector('button:has-text("Onboarding Wizard")')
            if wizard_btn:
                wizard_btn.click()
                print("[3] Provider Onboarding Wizard opened!", flush=True)
        except Exception as e:
            print(f"[!] Could not auto-click wizard: {e}", flush=True)

        # Tab 2: OmniRoute Combos
        page_combos = context.new_page()
        print(f"[4] Opening OmniRoute Combos: {OMNIROUTE_URL}/dashboard/combos", flush=True)
        page_combos.goto(f"{OMNIROUTE_URL}/dashboard/combos", wait_until="domcontentloaded")

        # Bring providers tab to front
        page_providers.bring_to_front()

        print("\n" + "=" * 70, flush=True)
        print("  CHROME WINDOW IS OPEN ON YOUR SCREEN!", flush=True)
        print("  You can now type credentials, log in to accounts, and add providers.", flush=True)
        print("  Press Ctrl+C in this terminal when you are done.", flush=True)
        print("=" * 70, flush=True)

        try:
            while len(context.pages) > 0:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nExiting assistant...", flush=True)
        finally:
            browser.close()

if __name__ == "__main__":
    main()
