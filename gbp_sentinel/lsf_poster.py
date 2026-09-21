"""Automated poster for Local Search Forum (Sterling Sky) via Playwright."""

import sys
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

SESSION_PATH = Path("data/lsf_session.json")
POST_URL = "https://localsearchforum.com/forums/spam-on-google.109/post-thread"
LOGIN_URL = "https://localsearchforum.com/login/"


def save_session():
    """Launch interactive browser for one-time manual login and save session state."""
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    print("==================================================================")
    print("ONE-TIME SETUP: LOCAL SEARCH FORUM (STERLING SKY) LOGIN")
    print("==================================================================")
    print("Er opent nu een browservenster.")
    print("1. Log in met je anonieme Local Search Forum account.")
    print("2. Zodra je bent ingelogd op het forum, detecteert het script dit automatisch.")
    print("3. De sessie-cookies worden opgeslagen in data/lsf_session.json.")
    print("==================================================================")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="en-US")
        page = context.new_page()
        page.goto(LOGIN_URL)

        # Wait up to 5 minutes for successful login by verifying xf_user cookie
        try:
            print("Wachten tot je succesvol bent ingelogd in het browservenster...")
            logged_in = False
            for _ in range(150):
                page.wait_for_timeout(2000)
                cookies = context.cookies()
                if any(c['name'] == 'xf_user' for c in cookies):
                    logged_in = True
                    break
            
            if logged_in:
                # Give browser a moment to persist all cookies
                page.wait_for_timeout(1500)
                context.storage_state(path=str(SESSION_PATH))
                print("\n*** SUCCES: Inloggen gedetecteerd! Sessie opgeslagen in data/lsf_session.json ***")
                print("Vanaf nu kan GBP Sentinel 100% autonoom en headless posten.")
            else:
                print("\nGeen voltooide login gedetecteerd binnen 5 minuten.")
        except Exception as e:
            print(f"\nFout tijdens inlogsessie: {e}")
        finally:
            browser.close()


def post_thread(title: str, body: str, headless: bool = True) -> str:
    """Post an escalation thread to Local Search Forum using saved session."""
    if not SESSION_PATH.exists():
        raise FileNotFoundError(
            f"Sessiebestand {SESSION_PATH} niet gevonden. "
            "Draai eerst 'python -m gbp_sentinel.lsf_poster --login' voor de eenmalige login."
        )

    print(f"Plaatsen van thread op Local Search Forum: '{title}'...")
    thread_url = ""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(SESSION_PATH), locale="en-US")
        page = context.new_page()
        
        page.goto(POST_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        # Verify logged in
        if "login" in page.url:
            browser.close()
            raise PermissionError("Sessie is verlopen. Voer opnieuw '--login' uit.")

        # Fill title
        page.fill('input[name="title"]', title)
        page.wait_for_timeout(500)

        # Toggle BBCode mode in Froala editor to allow raw text insertion
        bbcode_btn = page.locator('button[data-cmd="xfBbCode"], button[title*="BB code"]')
        if bbcode_btn.count() > 0:
            try:
                bbcode_btn.first.click()
                page.wait_for_timeout(500)
            except Exception:
                pass

        # Fill body
        msg_area = page.locator('textarea[name="message"]')
        if msg_area.count() > 0 and msg_area.first.is_visible():
            msg_area.first.fill(body)
        else:
            # Inject into WYSIWYG editor directly
            page.locator('.fr-element.fr-view').first.fill(body)

        page.wait_for_timeout(1000)

        # Click submit
        submit_btn = page.locator('button.button--primary:has-text("Post thread"), button:has-text("Post thread")')
        submit_btn.first.click()
        page.wait_for_timeout(4000)

        thread_url = page.url
        print(f"*** Thread succesvol geplaatst! Live URL: {thread_url} ***")
        browser.close()

    return thread_url


if __name__ == "__main__":
    if "--login" in sys.argv:
        save_session()
    else:
        print("Gebruik:")
        print("  python -m gbp_sentinel.lsf_poster --login       (Eenmalig inloggen & sessie opslaan)")
