"""Automated poster for Local Search Forum (Sterling Sky) via Playwright."""

import sys
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

SESSION_PATH = Path("data/lsf_session.json")
POST_URL = "https://localsearchforum.com/forums/spam-on-google.109/post-thread"
LOGIN_URL = "https://localsearchforum.com/login/"
DEFAULT_THREAD_URL = "https://localsearchforum.com/threads/massive-coordinated-google-maps-spam-syndicate-across-the-netherlands-918-listings-64-redressal-case-ids.63398/"


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

        if "login" in page.url:
            browser.close()
            raise PermissionError("Sessie is verlopen. Voer opnieuw '--login' uit.")

        page.fill('textarea[name="title"], input[name="title"]', title)
        page.wait_for_timeout(500)

        bbcode_btn = page.locator('button[data-cmd="xfBbCode"], button[title*="BB code"]')
        if bbcode_btn.count() > 0:
            try:
                bbcode_btn.first.click()
                page.wait_for_timeout(500)
            except Exception:
                pass

        msg_area = page.locator('textarea[name="message"]')
        if msg_area.count() > 0 and msg_area.first.is_visible():
            msg_area.first.fill(body)
        else:
            page.locator('.fr-element.fr-view').first.fill(body)

        page.wait_for_timeout(1000)

        submit_btn = page.locator('button:has-text("Create New Thread"), button.button--primary:has-text("Post thread"), button.button--icon--write')
        submit_btn.first.click()
        page.wait_for_timeout(6000)

        thread_url = page.url
        print(f"*** Thread succesvol geplaatst! Live URL: {thread_url} ***")
        browser.close()

    return thread_url


def post_reply(body: str, thread_url: str = DEFAULT_THREAD_URL, headless: bool = True) -> bool:
    """Post a reply to an existing Local Search Forum thread using saved session."""
    if not SESSION_PATH.exists():
        raise FileNotFoundError(f"Sessiebestand {SESSION_PATH} niet gevonden.")

    print(f"Plaatsen van reactie op thread: {thread_url}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(SESSION_PATH), locale="en-US")
        page = context.new_page()

        page.goto(thread_url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        if "login" in page.url:
            browser.close()
            raise PermissionError("Sessie is verlopen. Voer opnieuw '--login' uit.")

        bbcode_btn = page.query_selector("button[data-cmd='xfBbCode']")
        if bbcode_btn:
            bbcode_btn.click()
            page.wait_for_timeout(500)

        textarea = page.query_selector("textarea[name='message']")
        if textarea and textarea.is_visible():
            textarea.fill(body)
        else:
            fr_view = page.query_selector(".fr-element.fr-view")
            if fr_view:
                fr_view.fill(body)
            else:
                browser.close()
                return False

        page.wait_for_timeout(1000)

        post_btn = page.query_selector("button:has-text('Post reply')")
        if post_btn:
            post_btn.click()
            page.wait_for_timeout(5000)
            browser.close()
            return True

        browser.close()
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Gebruik:")
        print("  python -m gbp_sentinel.lsf_poster --login")
        print("  python -m gbp_sentinel.lsf_poster --post <title> <body_file>")
        print("  python -m gbp_sentinel.lsf_poster --reply <reply_file> [thread_url]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "--login":
        save_session()

    elif command == "--post":
        if len(sys.argv) < 4:
            print("Gebruik: python -m gbp_sentinel.lsf_poster --post <title> <body_file>")
            sys.exit(1)
        title = sys.argv[2]
        body_file = Path(sys.argv[3])
        if not body_file.exists():
            print(f"Bestand niet gevonden: {body_file}")
            sys.exit(1)
        body = body_file.read_text(encoding="utf-8")
        try:
            url = post_thread(title, body)
            print(f"Thread URL: {url}")
        except (FileNotFoundError, PermissionError) as e:
            print(f"Fout: {e}")
            sys.exit(1)

    elif command == "--reply":
        if len(sys.argv) < 3:
            print("Gebruik: python -m gbp_sentinel.lsf_poster --reply <reply_file> [thread_url]")
            sys.exit(1)
        reply_file = Path(sys.argv[2])
        if not reply_file.exists():
            print(f"Bestand niet gevonden: {reply_file}")
            sys.exit(1)
        body = reply_file.read_text(encoding="utf-8")
        thread_url = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_THREAD_URL
        try:
            success = post_reply(body, thread_url)
        except (FileNotFoundError, PermissionError) as e:
            print(f"Fout: {e}")
            sys.exit(1)
        if success:
            print("*** Reactie succesvol geplaatst! ***")
        else:
            print("Plaatsen van reactie mislukt.")
            sys.exit(1)

    else:
        print(f"Onbekend commando: {command}")
        print("Gebruik: --login | --post <title> <body_file> | --reply <reply_file> [thread_url]")
        sys.exit(1)
