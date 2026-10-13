"""Multi-location chain auditor & H1-grounded GBP name sanitizer.

Scrapes franchise and chain branch networks (e.g. Financieel Fit),
extracts verified landing page H1 / Schema ground truth, matches live Google Business Profiles,
and prepares/executes batch name edits.
"""

from __future__ import annotations

import asyncio
import json
import re
import urllib.request
from pathlib import Path
from typing import Any
from bs4 import BeautifulSoup

from . import config, db
from .maps_editor import MapsEditor
from .name_sanitizer import NameSanitizer
from .remediation_engine import RemediationEngine


class ChainAuditor:
    """Audits multi-location chains and compares live GBP titles against website H1s."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.sanitizer = NameSanitizer()
        self.remediation = RemediationEngine(headless=headless)
        self.editor = MapsEditor(headless=headless)
        db.init_db()

    def scrape_chain_vestigingen(self, overview_url: str = "https://www.financieelfit.nl/vestigingen/") -> list[dict[str, Any]]:
        """Scrapes all individual branch URLs and metadata from the chain overview page."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept-Language": "nl-NL,nl;q=0.9",
        }
        req = urllib.request.Request(overview_url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            soup = BeautifulSoup(resp.read().decode("utf-8"), "html.parser")
            links = [
                a.get("href")
                for a in soup.find_all("a")
                if a.get("href") and "/vestigingen/" in a.get("href") and a.get("href") not in ["/vestigingen/", overview_url]
            ]
            unique_links = sorted(list(set(links)))

        vestigingen = []
        for link in unique_links:
            # Resolve relative URLs if needed
            full_url = link if link.startswith("http") else f"https://www.financieelfit.nl{link}"
            slug = full_url.rstrip("/").split("/")[-1]
            city_guess = slug.replace("-", " ").title()
            vestigingen.append({
                "slug": slug,
                "url": full_url,
                "city_guess": city_guess
            })

        return vestigingen

    def fetch_branch_details(self, branch_url: str) -> dict[str, Any]:
        """Fetches a single branch landing page to extract H1, Schema.org data, and contact info."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept-Language": "nl-NL,nl;q=0.9",
        }
        req = urllib.request.Request(branch_url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            soup = BeautifulSoup(resp.read().decode("utf-8"), "html.parser")

        h1 = soup.find("h1")
        h1_text = h1.get_text(strip=True) if h1 else ""

        # Schema extraction
        schema_name = ""
        telephone = ""
        street = ""
        city = ""
        postal_code = ""

        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string)
                items = data.get("@graph", [data]) if isinstance(data, dict) else []
                for item in items:
                    if isinstance(item, dict) and item.get("@type") in ["FinancialService", "LocalBusiness"]:
                        schema_name = item.get("name") or schema_name
                        telephone = item.get("telephone") or telephone
                        addr = item.get("address", {})
                        if isinstance(addr, dict):
                            street = addr.get("streetAddress") or street
                            city = addr.get("addressLocality") or city
                            postal_code = addr.get("postalCode") or postal_code
            except Exception:
                pass

        maps_links = [
            a.get("href")
            for a in soup.find_all("a")
            if a.get("href") and ("google.com/maps" in a.get("href") or "goo.gl" in a.get("href"))
        ]

        return {
            "url": branch_url,
            "h1": h1_text,
            "schema_name": schema_name,
            "telephone": telephone,
            "address": f"{street}, {postal_code} {city}".strip(", "),
            "city": city,
            "maps_url": maps_links[0] if maps_links else ""
        }

    def audit_branch(self, gbp_listing: dict[str, Any], branch_meta: dict[str, Any]) -> dict[str, Any]:
        """Compares a live GBP profile against the official branch landing page H1."""
        raw_title = gbp_listing.get("title") or gbp_listing.get("name") or ""
        landing_h1 = branch_meta.get("h1") or ""
        schema_name = branch_meta.get("schema_name") or ""
        website_url = branch_meta.get("url") or ""

        analysis = self.sanitizer.sanitize(
            raw_title=raw_title,
            website_url=website_url,
            landing_h1=landing_h1,
            schema_name=schema_name
        )

        return {
            "branch_url": website_url,
            "city": branch_meta.get("city") or branch_meta.get("city_guess"),
            "landing_h1": landing_h1,
            "schema_name": schema_name,
            "gbp_title": raw_title,
            "gbp_url": gbp_listing.get("url") or "",
            "action": analysis["action"],
            "proposed_name": analysis["clean_name"],
            "confidence": analysis["confidence"],
            "stuffed_parts": analysis["removed_parts"],
            "reasons": analysis["reasons"]
        }
