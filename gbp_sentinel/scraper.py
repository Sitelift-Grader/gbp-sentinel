"""Google Maps and web sitemap scraper for Google Business Profiles."""

import asyncio
import re
import urllib.parse
from typing import List, Dict
from playwright.async_api import async_playwright
from . import config

class GbpScraper:
    def __init__(self, headless: bool = True):
        self.headless = headless

    async def scrape_maps(self, queries: List[str], delay_per_query: float = 3.0) -> Dict[str, dict]:
        """Scrape Google Maps for business profiles across multiple queries, deduplicating by place key."""
        unique_profiles = {}

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                user_agent=config.USER_AGENT,
                locale=config.CONFIG.get("browser_locale", "nl-NL")
            )
            page = await context.new_page()

            # Accept cookies once
            try:
                await page.goto("https://www.google.com/maps", wait_until="networkidle", timeout=15000)
                btn = await page.query_selector('button:has-text("Alles accepteren"), form[action*="consent"] button')
                if btn:
                    await btn.click()
                    await page.wait_for_timeout(1500)
            except Exception:
                pass

            for query in queries:
                encoded_q = urllib.parse.quote(query)
                search_url = f"https://www.google.com/maps/search/{encoded_q}"
                
                try:
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(int(delay_per_query * 1000))
                except Exception:
                    continue

                current_url = page.url
                if "/maps/place/" in current_url:
                    h1 = await page.evaluate("() => document.querySelector('h1')?.innerText")
                    body = await page.evaluate("() => document.body.innerText")
                    addr_btn = await page.evaluate("() => document.querySelector('button[data-item-id=\"address\"]')?.innerText.trim() || document.querySelector('[aria-label*=\"Adres:\"]')?.getAttribute('aria-label')?.replace('Adres: ', '').trim() || ''")
                    lines = [l.strip() for l in body.split("\n") if l.strip()]
                    addr = addr_btn if addr_btn else next((l for l in lines if re.search(r'\d{4}\s*[A-Z]{2}', l)), "Address unverified")
                    phone = next((l for l in lines if re.search(r'^(085|06|070|010|020|030|035|\+31)', l) and len(l) < 25), "")

                    place_key = re.search(r'1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', current_url)
                    key = place_key.group(1) if place_key else current_url

                    unique_profiles[key] = {
                        "name": h1 or query,
                        "url": current_url,
                        "address": addr,
                        "phone": phone,
                        "place_id": key,
                        "snippet": f"{h1} | {addr} | {phone}",
                        "query": query
                    }
                else:
                    items = await page.evaluate('''() => {
                        const res = [];
                        const articles = Array.from(document.querySelectorAll('div[role="article"]'));
                        for (const art of articles) {
                            const link = art.querySelector('a[href*="/maps/place/"]');
                            if (!link) continue;
                            const href = link.href;
                            const text = art.innerText || '';
                            const h1 = link.getAttribute('aria-label') || art.querySelector('.fontHeadlineSmall')?.innerText || '';
                            res.push({ name: h1, href, text });
                        }
                        if (res.length === 0) {
                            const links = Array.from(document.querySelectorAll('a[href*="/maps/place/"]'));
                            for (const a of links) {
                                const aria = a.getAttribute('aria-label') || '';
                                const parent = a.closest('div[role="feed"] > div') || a.parentElement;
                                res.push({ name: aria, href: a.href, text: parent ? parent.innerText : '' });
                            }
                        }
                        return res;
                    }''')

                    for item in items:
                        href = item.get("href", "")
                        m = re.search(r'1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', href)
                        key = m.group(1) if m else href
                        if not key:
                            continue

                        text = item.get("text", "")
                        lines = [l.strip() for l in text.split("\n") if l.strip()]
                        addr = "Address unverified"
                        phone = ""
                        for l in lines:
                            if re.search(r'\d{4}\s*[A-Z]{2}', l) or any(s in l.lower() for s in ["straat", "weg", "laan", "plein", "dijk", "park", "pad", "gracht", "kade", "singel", "weena"]):
                                addr = re.sub(r'^.*?[·\•]\s*', '', l).strip()
                            if re.search(r'(085|06|070|010|020|030|035|\+31)', l) and len(l) < 25:
                                phone = l

                        unique_profiles[key] = {
                            "name": item.get("name", query),
                            "url": href,
                            "address": addr,
                            "phone": phone,
                            "place_id": key,
                            "snippet": text.replace("\n", " | ")[:180],
                            "query": query
                        }

            await browser.close()

        return unique_profiles

    def run_search(self, queries: List[str]) -> List[dict]:
        """Synchronous wrapper for scrape_maps."""
        profiles_dict = asyncio.run(self.scrape_maps(queries))
        return list(profiles_dict.values())
