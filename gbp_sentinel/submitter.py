"""Headless Playwright submitter for Google Business Redressal Form."""

import asyncio
import os
import re
from pathlib import Path
from playwright.async_api import async_playwright
from . import config

FORM_URL = "https://support.google.com/business/contact/business_redressal_form?hl=en"

class RedressalSubmitter:
    def __init__(self, headless: bool = None):
        self.headless = config.HEADLESS if headless is None else headless

    async def submit(
        self,
        target_name: str,
        csv_path: Path,
        explanation_text: str,
        public_url: str = "",
        activity_type: str = "address"
    ) -> dict:
        """Submit the redressal complaint to Google and extract the Case ID."""
        csv_path = Path(csv_path).resolve()
        if not csv_path.exists():
            raise FileNotFoundError(f"Dossier CSV not found at {csv_path}")

        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in target_name).lower()
        filled_screenshot = config.SCREENSHOTS_DIR / f"{safe_name}_form_filled.png"
        result_screenshot = config.SCREENSHOTS_DIR / f"{safe_name}_submission_result.png"

        result = {
            "success": False,
            "case_id": None,
            "filled_screenshot": str(filled_screenshot),
            "result_screenshot": str(result_screenshot),
            "message": ""
        }

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                user_agent=config.USER_AGENT,
                locale=config.CONFIG.get("browser_locale", "nl-NL")
            )
            page = await context.new_page()

            await page.goto(FORM_URL, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            # Fill Submitter Details
            await page.fill("#full_name", config.SUBMITTER_NAME)
            await page.fill("#email_address", config.SUBMITTER_EMAIL)
            await page.fill("#organization_name", config.SUBMITTER_ORG)

            # Select fraudulent activity
            await page.evaluate(f'''() => {{
                const select = document.querySelector('select[name="fraudulent_activity"]');
                if (select) {{
                    select.value = '{activity_type}';
                    select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
                const customSelect = document.querySelector('.sc-select#fraudulent_activity span');
                if (customSelect) {{
                    customSelect.innerText = '{activity_type.capitalize()}';
                }}
            }}''')

            # Fill Public URL
            if not public_url:
                public_url = f"https://www.google.com/maps/search/?api=1&query={target_name}"
            if "google.nl/maps" in public_url:
                public_url = public_url.replace("google.nl/maps", "google.com/maps")
            if "?" in public_url and "api=1" not in public_url:
                public_url = public_url.split("?")[0]
            if not public_url.startswith("https://www.google.com/maps"):
                public_url = f"https://www.google.com/maps/search/?api=1&query={target_name}"
            await page.fill("#public_url", public_url)

            # Upload CSV Dossier
            file_input = await page.query_selector("input#url_upload")
            if file_input:
                await file_input.set_input_files(str(csv_path))
                await page.wait_for_timeout(1500)

            # Fill Explanation Text
            await page.fill("#malicious_on_google_maps", explanation_text)
            await page.wait_for_timeout(1500)

            # Check Feedback Checkbox
            await page.evaluate('''() => {
                const cb = document.querySelector('input[type="checkbox"]');
                if (cb && !cb.checked) {
                    cb.click();
                }
            }''')

            # Take screenshot of filled form
            await page.screenshot(path=str(filled_screenshot), full_page=True)

            # Click Submit button
            submit_btn = await page.query_selector("button.submit-button")
            if not submit_btn:
                submit_btn = await page.query_selector(".submit-button")

            if submit_btn:
                await submit_btn.click(force=True)
                await page.wait_for_timeout(6000)

                page_text = await page.evaluate("() => document.body.innerText")
                if "We couldn't submit your form yet" in page_text or "Please enter a valid URL" in page_text:
                    result["success"] = False
                    result["message"] = "Form validation error on page."
                else:
                    case_match = re.search(r'\b([0-9]-[0-9]{10,16})\b', page_text)
                    if case_match:
                        result["case_id"] = case_match.group(1)
                        result["success"] = True
                        result["message"] = f"Submitted successfully! Google Case ID: {result['case_id']}"
                    elif any(kw.lower() in page_text.lower() for kw in ["thank you", "your email has been sent", "case id"]):
                        result["success"] = True
                        result["message"] = "Submitted successfully! Check email for Case ID confirmation."
                    else:
                        result["message"] = "Submit button clicked, but confirmation text was not recognized."

                await page.screenshot(path=str(result_screenshot), full_page=True)
            else:
                result["message"] = "Submit button not found on form page."

            await browser.close()

        return result

    def run_submit(self, target_name: str, csv_path: Path, explanation_text: str, public_url: str = "") -> dict:
        """Synchronous wrapper for submit."""
        return asyncio.run(self.submit(target_name, csv_path, explanation_text, public_url))
