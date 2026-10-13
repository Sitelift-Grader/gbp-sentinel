#!/usr/bin/env python3
"""Audit & H1-Grounded Sanitize Script voor Financieel Fit.

Scrapet de vestigingen van Financieel Fit, vergelijkt de officiële H1 / Schema
met de live profielnamen op Google Maps, en bereidt bewerkingsvoorstellen voor.
"""

import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gbp_sentinel import db
from gbp_sentinel.chain_auditor import ChainAuditor
from gbp_sentinel.maps_editor import MapsEditor
from playwright.async_api import async_playwright


async def resolve_gmaps_profile(page, query: str) -> dict:
    """Zoekt een vestiging op Google Maps en haalt de live profielgegevens op."""
    url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(3000)

        # Cookie acceptatie indien nodig
        try:
            btn = page.locator('button:has-text("Alles accepteren"), form[action*="consent"] button')
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(1500)
        except Exception:
            pass

        current_url = page.url
        title_el = page.locator('h1.DUwDvf, h1')
        title = ""
        if await title_el.count() > 0:
            title = await title_el.first.inner_text()

        # Als er een lijst met resultaten is, klik op de eerste kaart
        if title == "Resultaten" or not title:
            first_card = page.locator('div[role="feed"] a[href*="/maps/place/"], div.Nv2PK a[href*="/maps/place/"], a[href*="/maps/place/"]').first
            if await first_card.count() > 0:
                await first_card.click()
                await page.wait_for_timeout(2500)
                current_url = page.url
                place_h1 = page.locator('h1.DUwDvf, h1')
                if await place_h1.count() > 0:
                    title = await place_h1.first.inner_text()

        return {
            "title": title.strip(),
            "url": current_url,
            "query": query
        }
    except Exception as e:
        return {
            "title": "",
            "url": "",
            "query": query,
            "error": str(e)
        }


async def main():
    parser = argparse.ArgumentParser(description="Financieel Fit GBP Audit & H1 Sanitize Runner")
    parser.add_argument("--vestiging", type=str, default="", help="Filter op specifieke vestiging/stad (bijv. 'weert' of 'almere')")
    parser.add_argument("--limit", type=int, default=10, help="Aantal vestigingen om te auditen (default: 10, 0 voor alle 90)")
    parser.add_argument("--execute", action="store_true", help="Voer bewerkingsvoorstellen daadwerkelijk uit via Google Maps")
    parser.add_argument("--save-db", action="store_true", default=True, help="Sla bewerkingsvoorstellen op in de database")
    args = parser.parse_args()

    auditor = ChainAuditor()
    print("[1/4] Vestigingenlijst ophalen van financieelfit.nl/vestigingen/ ...")
    vestigingen = auditor.scrape_chain_vestigingen()
    print(f"      Gevonden: {len(vestigingen)} vestigingen.")

    if args.vestiging:
        query_v = args.vestiging.lower().strip()
        vestigingen = [v for v in vestigingen if query_v in v["slug"].lower() or query_v in v["city_guess"].lower()]
        print(f"      Gefilterd op '{args.vestiging}': {len(vestigingen)} vestigingen gevonden.")
    elif args.limit > 0:
        vestigingen = vestigingen[:args.limit]
        print(f"      Audit beperkt tot eerste {len(vestigingen)} vestigingen (--limit {args.limit}).")

    results = []
    print("\n[2/4] Landingspagina's en Google Maps profielen scannen...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(locale="nl-NL")

        # Accept cookies once on Maps
        try:
            await page.goto("https://www.google.com/maps", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)
            btn = page.locator('button:has-text("Alles accepteren"), form[action*="consent"] button')
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(1500)
        except Exception:
            pass

        for i, vest in enumerate(vestigingen, start=1):
            v_url = vest["url"]
            print(f"  [{i}/{len(vestigingen)}] Fetching: {v_url}")
            try:
                meta = auditor.fetch_branch_details(v_url)
            except Exception as e:
                print(f"      Fout bij ophalen pagina: {e}")
                continue

            city_name = meta.get("city") or vest.get("city_guess") or ""
            query = f"Financieel Fit {city_name}".strip()
            gmaps_data = await resolve_gmaps_profile(page, query)

            audit_item = auditor.audit_branch(gmaps_data, meta)
            results.append(audit_item)

            print(f"      Website H1:  '{audit_item['landing_h1']}'")
            print(f"      Maps Titel:  '{audit_item['gbp_title']}'")
            print(f"      Actie:       {audit_item['action']} -> Voorstel: '{audit_item['proposed_name']}'")
            if audit_item['stuffed_parts']:
                print(f"      Spam gestript: {audit_item['stuffed_parts']}")
            print()

        await browser.close()

    # Save to DB
    if args.save_db:
        print("[3/4] Opslaan in Sentinel database (profile_edits)...")
        conn = db._get_connection()
        try:
            with conn:
                for item in results:
                    if item["action"] == "RENAME" and item["gbp_url"]:
                        conn.execute("""
                            INSERT INTO profile_edits 
                            (place_url, original_title, sanitized_title, action_type, remediation_track, status, notes)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            item["gbp_url"],
                            item["gbp_title"],
                            item["proposed_name"],
                            "RENAME",
                            "MAPS_EDIT",
                            "proposed",
                            f"H1 Ground Truth: {item['landing_h1']} | Gestript: {', '.join(item['stuffed_parts'])}"
                        ))
        finally:
            conn.close()

    # Export Report
    output_dir = Path("dossiers/financieel_fit")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_csv = output_dir / f"audit_financieel_fit_{timestamp}.csv"

    with open(report_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "city", "branch_url", "landing_h1", "schema_name", "gbp_title", "proposed_name", "action", "confidence", "stuffed_parts", "gbp_url"
        ])
        writer.writeheader()
        for r in results:
            writer.writerow({
                "city": r["city"],
                "branch_url": r["branch_url"],
                "landing_h1": r["landing_h1"],
                "schema_name": r["schema_name"],
                "gbp_title": r["gbp_title"],
                "proposed_name": r["proposed_name"],
                "action": r["action"],
                "confidence": r["confidence"],
                "stuffed_parts": " | ".join(r["stuffed_parts"]),
                "gbp_url": r["gbp_url"]
            })

    print(f"[4/4] Rapport succesvol gegenereerd: {report_csv}")
    print(f"      Totaal geanalyseerd: {len(results)}")
    renames = [r for r in results if r["action"] == "RENAME"]
    print(f"      Gevallen met keyword stuffing / edits nodig: {len(renames)} ({len(renames)/len(results)*100:.1f}%)")


if __name__ == "__main__":
    asyncio.run(main())
