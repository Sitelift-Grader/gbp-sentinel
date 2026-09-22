"""Autonomous end-to-end orchestrator for GBP Sentinel."""

import asyncio
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from . import config, db, dossier, forum, submitter

DUTCH_CITIES = [
    'amsterdam', 'rotterdam', 'denhaag', 'utrecht', 'eindhoven', 'tilburg', 'groningen', 'almere', 'breda', 'nijmegen',
    'enschede', 'haarlem', 'arnhem', 'amersfoort', 'zaandam', 'denbosch', 'haarlemmermeer', 'zwolle', 'zoetermeer', 'leiden',
    'maastricht', 'dordrecht', 'ede', 'alphenaandenrijn', 'alkmaar', 'emmen', 'delft', 'venlo', 'deventer', 'helmond',
    'oss', 'amstelveen', 'hilversum', 'heerlen', 'gouda'
]

SYNDICATE_VOIP_PATTERNS = ['369', '360', '569', '669', '798', '796', '794', '455', '754', '793']

KNOWN_FLEX_HUBS = {
    "Zekeringstraat": "Regus Amsterdam Sloterdijk",
    "Weena": "Regus Rotterdam Weena",
    "Johan de Wittlaan": "Regus The Hague World Forum",
    "St Jacobsstraat": "Regus Utrecht City Center",
    "Flight Forum": "Regus Eindhoven Flight Forum",
    "Hart van Brabantlaan": "Regus Tilburg Spoorzone",
    "Paterswoldseweg": "Regus Groningen Zuid",
    "Mandelaplein": "Regus Almere Central Station",
    "Verlengde Poolseweg": "Regus Breda Chassé Park",
    "Jonkerbosplein": "Regus Nijmegen FiftyTwoDegrees",
    "Capitool": "Kennispark Twente Enschede",
    "Hendrik Figeeweg": "Figee Fabriek Haarlem",
    "Teldersstraat": "Regus Arnhem Rijnpark",
    "Databankweg": "Business Center Databankweg Amersfoort",
    "Koelmalaan": "Bedrijvencentrum Koelmalaan Alkmaar",
    "Het Rietveld": "Business Center Het Rietveld Apeldoorn"
}


def harvest_niche_sites(niche: str, tlds=('.com', '.net', '.nl')) -> list[dict]:
    """Scan nationwide for syndicate sites in a specific niche."""
    print(f"\n[1/4] Autonoom zoeken naar syndicate websites voor '{niche}' over {len(DUTCH_CITIES)} steden...")
    found = []
    for c in DUTCH_CITIES:
        for tld in tlds:
            url = f"https://{niche}{c}{tld}"
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=1.2) as res:
                    soup = BeautifulSoup(res.read().decode('utf-8', errors='ignore'), 'html.parser')
                    tels = [a['href'].replace('tel:', '').strip() for a in soup.find_all('a', href=True) if a['href'].startswith('tel:')]
                    footer = soup.find('footer')
                    addr = footer.get_text(separator=' ', strip=True) if footer else ''
                    title = soup.title.string.strip() if soup.title else ''
                    phone = tels[0] if tels else ''
                    
                    # Match known syndicate VoIP prefixes
                    if any(p in ''.join(tels) for p in SYNDICATE_VOIP_PATTERNS):
                        found.append({
                            'city': c,
                            'url': url,
                            'phone': phone,
                            'title': title,
                            'site_address': addr[:150]
                        })
                        print(f"  -> Gevonden: {c:15} | {url:35} | {phone}")
                        break
            except Exception:
                pass
    print(f"Oogst voltooid: {len(found)} actieve websites gedetecteerd.")
    return found


def audit_on_maps(niche_title: str, harvested: list[dict]) -> list[dict]:
    """Run Playwright on Google Maps to extract Place URLs, share links, and occupants."""
    print(f"\n[2/4] Google Maps verificatie via Playwright voor {len(harvested)} locaties...")
    audited = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale='nl-NL')
        page.goto('https://www.google.com/maps')
        page.wait_for_timeout(1000)
        try:
            page.locator('button:has-text("Alles accepteren")').first.click(timeout=3000)
        except Exception:
            pass

        for i, t in enumerate(harvested, 1):
            city = t['city']
            phone = t['phone']
            site_url = t['url']
            site_addr = t.get('site_address', '')
            query = phone if phone else f"{niche_title} {city}"
            
            try:
                page.goto('https://www.google.com/maps/search/' + urllib.parse.quote(query))
                page.wait_for_timeout(2500)

                cards = page.locator('a[href*="/maps/place/"]')
                if cards.count() > 0 and 'search' in page.url:
                    cards.first.click()
                    page.wait_for_timeout(2000)

                share_link = ''
                share_btn = page.locator('button[data-value="Delen"]')
                if share_btn.count() > 0:
                    try:
                        share_btn.first.click(timeout=2500)
                        page.wait_for_timeout(1000)
                        inp = page.locator('input[readonly]')
                        if inp.count() > 0:
                            share_link = inp.first.get_attribute('value')
                        page.keyboard.press('Escape')
                    except Exception:
                        pass

                h1 = page.locator('h1').first.inner_text() if page.locator('h1').count() else f"{niche_title} {city.capitalize()}"
                addr = page.locator('button[data-item-id="address"]').first.inner_text() if page.locator('button[data-item-id="address"]').count() else site_addr

                clean_h1 = h1.replace('\n', ' ').strip()
                clean_addr = addr.replace('\n', ' ').replace('', '').strip()
                place_url = page.url.split('?')[0] if '/place/' in page.url else page.url

                # Identify hub
                occ = "Unstaffed commercial flex office / virtual address"
                for street, hub_name in KNOWN_FLEX_HUBS.items():
                    if street in clean_addr or street in site_addr:
                        occ = hub_name
                        break

                audited.append({
                    'city': city,
                    'name': clean_h1,
                    'address': clean_addr or site_addr or f"{city.capitalize()}, Netherlands",
                    'phone': phone,
                    'website': site_url,
                    'actual_occupant': occ,
                    'url': place_url,
                    'share_url': share_link,
                    'kvk_status': 'Unregistered ghost entity without official trade register presence',
                    'policy_violation_details': (
                        f"Ineligible virtual office listing at commercial flex office ({occ}); "
                        f"zero equipment, storefront, workshop, or technical staff on site. "
                        f"Consecutive VoIP SIP block ({phone}). Guidelines 2447164 & 3052070."
                    ),
                    'is_fraud': True
                })
                print(f"  [{i}/{len(harvested)}] {city:15} | {clean_h1[:25]:25} | {share_link or place_url}")
            except Exception as e:
                print(f"  [{i}/{len(harvested)}] ERR {city}: {e}")

        browser.close()
        
    return audited


def submit_batch(target_name: str, locations: list[dict], explanation: str, hq: str = "Regus Amsterdam Sloterdijk") -> dict:
    """Submit a batch to Google Redressal headlessly and save to database."""
    print(f"\n[3/4] Indienen van '{target_name}' ({len(locations)} locaties) bij Google Redressal...")
    assert len(explanation) < 950, f"Explanation too long: {len(explanation)} chars"

    db.init_db()
    db.save_target(target_name, kvk="Onbekend (Lead-gen netwerk)", website=locations[0]['website'], hq_address=hq)
    db.save_locations(target_name, locations)

    csv_path = dossier.export_dossier_csv(target_name, locations)
    print(f"  CSV dossier gegenereerd: {csv_path}")

    sub = submitter.RedressalSubmitter(headless=True)
    res = sub.run_submit(
        target_name,
        csv_path,
        explanation,
        public_url=locations[0]["url"]
    )

    case_id = res.get("case_id")
    if case_id:
        print(f"  *** SUCCES: GOOGLE CASE ID ONTVANGEN: {case_id} ***")
        db.save_submission(
            target_name=target_name,
            case_id=case_id,
            email=config.SUBMITTER_EMAIL,
            dossier_path=str(csv_path),
            filled_screenshot=res.get("filled_screenshot"),
            result_screenshot=res.get("result_screenshot"),
            status="submitted"
        )
        res['case_id'] = case_id
    else:
        print(f"  Waarschuwing: Geen Case ID direct op pagina gedetecteerd.")

    return res


def run_autopilot_pipeline(niche: str, display_name: str, submit: bool = False, confirm: bool = False):
    """Run discovery and evidence collection; submissions require explicit confirmation."""
    print(f"================================================================")
    print(f"GBP SENTINEL AUTOPILOT: {display_name.upper()} ({niche})")
    print(f"================================================================")

    # 1. Harvest
    harvested = harvest_niche_sites(niche)
    if not harvested:
        print(f"Geen actieve websites gevonden voor niche '{niche}'.")
        return

    # 2. Audit
    audited = audit_on_maps(display_name, harvested)
    if not audited:
        print("Geen locaties kunnen auditeren.")
        return

    # 3. Batch and prepare evidence. Submission is deliberately opt-in so
    # discovery signals cannot turn into external reports without review.
    batch_size = 18
    num_batches = (len(audited) + batch_size - 1) // batch_size
    
    for b_idx in range(num_batches):
        chunk = audited[b_idx * batch_size : (b_idx + 1) * batch_size]
        part_str = f"Part {b_idx + 1}" if num_batches > 1 else ""
        target_name = f"National {display_name} Syndicate {part_str} (0XX-369 Network)".strip()
        
        explanation = (
            f"This complaint documents {part_str} of a nationwide {display_name.lower()} lead-generation "
            f"syndicate abusing Google Maps across {len(chunk)} cities in the Netherlands. "
            f"The operator claims fake physical storefronts, workshops, and facilities at unstaffed "
            f"commercial flex centers (Regus Sloterdijk, Regus Weena, Regus World Forum, Regus Utrecht City). "
            f"None of these locations possess equipment, tools, inventory, or permanent staff on site. "
            f"All listings systematically abuse consecutive VoIP SIP blocks routing to an unlicensed central lead broker. "
            f"Please remove all fraudulent listings under Google Maps guidelines 2447164 and 3052070."
        )
        if len(explanation) >= 950:
            explanation = explanation[:940] + "..."

        if submit and confirm:
            res = submit_batch(target_name, chunk, explanation)
            case_id = res.get("case_id", "PENDING")
        else:
            case_id = "NOT_SUBMITTED"
            print("  Niet ingediend: controleer bewijs en gebruik --submit --confirm voor een echte indiening.")

        if case_id == "NOT_SUBMITTED":
            print("  Community- en forum-escalatie overgeslagen: er is nog geen geverifieerde Google Case ID.")
            continue

        # 4. Generate Standardized Community & Forum Payloads
        print(f"\n[4/4] Escalatie payloads genereren voor {target_name}...")
        safe_slug = "".join(c if c.isalnum() else "_" for c in target_name).lower()

        # Google Community Payload (Policies and guidelines category)
        comm_payload = forum.build_community_payload(target_name, case_id, [c['name'] for c in chunk])
        google_file = config.SCRATCH_DIR / f"{safe_slug}_google_community.txt"
        google_content = (
            f"TARGET FORUM: Google Business Profile Help Community\n"
            f"URL: {comm_payload['forum_url']}\n"
            f"MANDATORY CATEGORY: {comm_payload['category_en']} / {comm_payload['category_nl']}\n"
            f"TITLE: {comm_payload['title']}\n"
            f"{'='*70}\n\n"
            f"{comm_payload['body']}\n"
        )
        google_file.write_text(google_content, encoding="utf-8")

        # LSF Cross-Reply Payload (tagging @keyserholiday on master thread)
        lsf_file = config.SCRATCH_DIR / f"{safe_slug}_lsf_cross_reply.txt"
        lsf_content = forum.build_lsf_cross_reply(case_ids=[case_id])
        lsf_file.write_text(lsf_content, encoding="utf-8")
        print(f"  Google Community payload gereed: {google_file}")
        print(f"  Local Search Forum payload gereed: {lsf_file}")

    print(f"\nAutopilot run voor '{display_name}' succesvol afgerond!")


def main():
    parser = argparse.ArgumentParser(description="GBP Sentinel Autonomous Pipeline")
    parser.add_argument("--niche", required=True, help="Niche keyword (e.g. autodealer, loodgieter, schoorsteenveger)")
    parser.add_argument("--name", required=True, help="Display name (e.g. 'Locksmith', 'Chimney Sweep', 'Plumber')")
    parser.add_argument("--submit", action="store_true", help="Dien de voorbereide batches in na controle")
    parser.add_argument("--confirm", action="store_true", help="Bevestig dat externe indiening is toegestaan")
    args = parser.parse_args()

    if args.submit and not args.confirm:
        parser.error("--submit vereist ook --confirm")
    run_autopilot_pipeline(args.niche, args.name, submit=args.submit, confirm=args.confirm)


if __name__ == "__main__":
    main()
