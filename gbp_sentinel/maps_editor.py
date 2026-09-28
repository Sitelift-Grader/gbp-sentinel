from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from playwright.async_api import async_playwright


class MapsEditor:
    """
    Automatisering voor 'Bewerking voorstellen' op Google Maps via Playwright.
    Ondersteunt persistente browserprofielen om ingelogde Google-sessies te behouden.
    """

    def __init__(self, user_data_dir: str = "data/google_profile", headless: bool = True):
        self.user_data_dir = Path(user_data_dir)
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.screenshots_dir = Path("screenshots/edits")
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    async def check_login_status(self) -> bool:
        """Controleert of er een actieve Google login aanwezig is in het profiel."""
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=True,
                locale="nl-NL"
            )
            page = await context.new_page()
            try:
                await page.goto("https://myaccount.google.com/", timeout=15000)
                await page.wait_for_timeout(2000)
                is_logged_in = "accounts.google.com/signin" not in page.url and await page.locator('a[aria-label*="Google-account"]').count() > 0
                return is_logged_in
            except Exception:
                return False
            finally:
                await context.close()

    async def open_interactive_login(self) -> None:
        """Opent een zichtbaar browservenster zodat de gebruiker eenmalig kan inloggen."""
        print("\n[MapsEditor] Zichtbaar browservenster wordt geopend voor Google login...")
        print("[MapsEditor] Log in met je Google Account. Sluit het venster wanneer je klaar bent.\n")
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=False,
                locale="nl-NL"
            )
            page = await context.new_page()
            await page.goto("https://accounts.google.com/signin")
            
            # Wacht tot de gebruiker de browser sluit of inlogt
            try:
                await page.wait_for_url("https://myaccount.google.com/**", timeout=300000)
                print("[MapsEditor] Inloggen succesvol gedetecteerd!")
            except Exception:
                print("[MapsEditor] Interactieve sessie beëindigd.")
            finally:
                await context.close()

    async def suggest_name_edit(self, place_url: str, new_name: str, edit_id: int = None) -> dict[str, Any]:
        """
        Dient een naamsverbetering in op Google Maps voor de opgegeven locatie.
        """
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=self.headless,
                locale="nl-NL"
            )
            page = await context.new_page()
            screenshot_path = ""
            
            try:
                # 1. Navigeer naar Google Maps locatie
                await page.goto(place_url, timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
                
                # Cookie acceptatie indien nodig
                try:
                    btn = page.locator('button:has-text("Alles accepteren"), form[action*="consent"] button')
                    if await btn.count() > 0:
                        await btn.first.click()
                        await page.wait_for_timeout(1000)
                except Exception:
                    pass

                # 2. Zoek de 'Bewerking voorstellen' knop
                edit_btn = page.locator('button:has-text("Bewerking voorstellen"), button[aria-label*="Bewerking voorstellen"], button:has-text("Suggest an edit")')
                if await edit_btn.count() == 0:
                    return {
                        "status": "failed",
                        "error": "Knop 'Bewerking voorstellen' niet gevonden op pagina",
                        "screenshot": ""
                    }

                await edit_btn.first.click()
                await page.wait_for_timeout(2000)

                # 3. Controleer op inlogverzoek
                login_prompt = page.locator('text="Log in om te beginnen", text="Sign in to continue"')
                if await login_prompt.count() > 0:
                    shot_path = str(self.screenshots_dir / f"login_required_{edit_id or 'test'}.png")
                    await page.screenshot(path=shot_path)
                    return {
                        "status": "login_required",
                        "error": "Google login vereist om bewerkingen in te dienen. Gebruik open_interactive_login() om in te loggen.",
                        "screenshot": shot_path
                    }

                # 4. Klik op 'Naam of andere gegevens wijzigen'
                name_menu = page.locator('div[role="menuitem"]:has-text("Naam"), div:has-text("Naam of andere gegevens wijzigen")')
                if await name_menu.count() > 0:
                    await name_menu.first.click()
                    await page.wait_for_timeout(2000)

                # 5. Pas het veld Bedrijfsnaam aan
                name_input = page.locator('input[aria-label*="Bedrijfsnaam"], input[aria-label*="Business name"], input[name*="name"]').first
                if await name_input.count() > 0:
                    # Selecteer alles en overschrijf met de nieuwe naam
                    await name_input.click()
                    await name_input.fill("")
                    await name_input.fill(new_name)
                    await page.wait_for_timeout(1000)

                    # 6. Klik op Verzenden
                    submit_btn = page.locator('button:has-text("Verzenden"), button:has-text("Submit")').first
                    if await submit_btn.count() > 0:
                        await submit_btn.click()
                        await page.wait_for_timeout(3000)

                    shot_path = str(self.screenshots_dir / f"edit_success_{edit_id or 'test'}.png")
                    await page.screenshot(path=shot_path)
                    return {
                        "status": "submitted",
                        "new_name": new_name,
                        "screenshot": shot_path
                    }
                else:
                    return {
                        "status": "failed",
                        "error": "Invoerveld 'Bedrijfsnaam' niet aangetroffen in bewerkingsdialoog",
                        "screenshot": ""
                    }

            except Exception as e:
                shot_path = str(self.screenshots_dir / f"edit_error_{edit_id or 'test'}.png")
                try:
                    await page.screenshot(path=shot_path)
                except Exception:
                    pass
                return {
                    "status": "failed",
                    "error": str(e),
                    "screenshot": shot_path
                }
            finally:
                await context.close()
