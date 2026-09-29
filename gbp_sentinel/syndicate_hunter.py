"""Leadgen syndicate discovery and footprint hunter for GBP Sentinel.

Identifies multi-site lead generation networks, affiliate rings, and deceptive contractor fronts
operating across the Netherlands by scanning technical footprints:
- Shared Google Tag Manager containers (GTM-XXXXXXX)
- Shared Google Analytics / GA4 properties (G-XXXXXXXXXX)
- Shared central VoIP / phone numbers (085-, 020-369, 010-360, etc.)
- Shared Chamber of Commerce (KvK) numbers
- Deceptive copy footprints (e.g. 'eigen betrouwbare monteurs', 'zonder externe partijen')
"""

import concurrent.futures
import csv
import re
import socket
import ssl
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from . import config, db

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


class SyndicateHunter:
    """Discovers and maps coordinated lead generation syndicates."""

    def __init__(self, timeout: int = 5, max_workers: int = 40):
        self.timeout = timeout
        self.max_workers = max_workers
        self.headers = {
            "User-Agent": config.USER_AGENT
        }

    def check_domain_dns(self, domain: str) -> Optional[Tuple[str, str]]:
        """Resolve DNS A record for a candidate domain."""
        try:
            ip = socket.gethostbyname(domain)
            return (domain, ip)
        except Exception:
            return None

    def inspect_domain_footprint(self, domain: str) -> Optional[Dict[str, Any]]:
        """Fetch domain HTML and extract tracking IDs, phone numbers, KvK, and CMS markers."""
        for proto in ["https", "http"]:
            url = f"{proto}://{domain}"
            try:
                req = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")

                    # Extract GTM, GA4, AdSense
                    gtm = set(re.findall(r"GTM-[A-Z0-9]+", html))
                    ga4 = set(re.findall(r"G-[A-Z0-9]{8,12}", html))
                    adsense = set(re.findall(r"ca-pub-[0-9]+", html))

                    # Extract Dutch KvK numbers (8 digits)
                    kvk_matches = re.findall(r"\b([0-9]{8})\b", html)
                    # Filter likely KvK context
                    kvk = set()
                    for k in kvk_matches:
                        if re.search(rf"(?:kvk|handelsregister|dossier)[^\d]{{0,25}}{k}", html, re.I):
                            kvk.add(k)

                    # Extract Dutch phone numbers (085, 088, 0800, regional 010, 020, etc.)
                    phones = set(re.findall(r"\b(085[\s\-]?[0-9]{3}[\s\-]?[0-9]{4}|088[\s\-]?[0-9]{3}[\s\-]?[0-9]{4}|0[1-9][0-9][\s\-]?[0-9]{3}[\s\-]?[0-9]{4})\b", html))

                    # Check for deceptive copy markers
                    deceptive_claims = []
                    lower_html = html.lower()
                    if "eigen monteur" in lower_html or "eigen betrouwbare monteurs" in lower_html:
                        deceptive_claims.append("Claimt eigen monteurs")
                    if "geen externe partij" in lower_html or "zonder externe partijen" in lower_html:
                        deceptive_claims.append("Claimt geen externe partijen")
                    if "eigen bussen" in lower_html or "eigen personeel" in lower_html:
                        deceptive_claims.append("Claimt eigen bussen/personeel")
                    if "exclusieve leads" in lower_html or "doorverkopen van persoonsgegevens" in lower_html:
                        deceptive_claims.append("Leadhandelaar marker")

                    # Title
                    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.DOTALL)
                    title = title_match.group(1).strip() if title_match else domain

                    return {
                        "domain": domain,
                        "url": url,
                        "title": title,
                        "gtm": sorted(list(gtm)),
                        "ga4": sorted(list(ga4)),
                        "adsense": sorted(list(adsense)),
                        "kvk": sorted(list(kvk)),
                        "phones": sorted(list(phones)),
                        "deceptive_claims": deceptive_claims,
                        "html_length": len(html)
                    }
            except Exception:
                continue
        return None

    def scan_pattern_matrix(
        self,
        keywords: List[str],
        patterns: List[str],
        target_gtm: Optional[str] = None,
        target_kvk: Optional[str] = None,
        target_phone: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Generate candidates across keyword-pattern matrix, test DNS and match footprint."""
        candidates = set()
        for kw in keywords:
            for pat in patterns:
                domain = pat.format(kw).strip().lower()
                candidates.add(domain)

        print(f"SyndicateHunter: Generated {len(candidates)} candidate domains to resolve...", flush=True)

        # 1. Resolve DNS
        live = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            dns_results = executor.map(self.check_domain_dns, candidates)
            for r in dns_results:
                if r:
                    live.append(r[0])

        print(f"SyndicateHunter: Found {len(live)} resolving domains in DNS. Analyzing footprints...", flush=True)

        # 2. Inspect footprints
        matches = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            footprints = executor.map(self.inspect_domain_footprint, live)
            for fp in footprints:
                if not fp:
                    continue

                is_match = False
                if target_gtm and target_gtm in fp["gtm"]:
                    is_match = True
                elif target_kvk and target_kvk in fp["kvk"]:
                    is_match = True
                elif target_phone and any(target_phone in p.replace(" ", "").replace("-", "") for p in fp["phones"]):
                    is_match = True
                elif not (target_gtm or target_kvk or target_phone):
                    # Unsupervised discovery: look for strong leadgen markers
                    if fp["deceptive_claims"] or len(fp["gtm"]) > 0 or len(fp["phones"]) > 0:
                        is_match = True

                if is_match:
                    matches.append(fp)

        print(f"SyndicateHunter: Discovered {len(matches)} matching syndicate domains!", flush=True)
        return matches

    def export_syndicate_dossier(
        self,
        syndicate_name: str,
        results: List[Dict[str, Any]],
        output_filename: str
    ) -> Path:
        """Save discovered syndicate domains into a standard GBP Sentinel CSV dossier."""
        out_dir = config.DOSSIERS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path = out_dir / output_filename

        fieldnames = [
            "Business Name on Profile",
            "Google Maps URL",
            "Reported Address",
            "Actual Occupant / True Business",
            "KvK Commercial Registry Status",
            "Specific Policy Violation Details"
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                name_clean = r["domain"].replace(".nl", "").replace(".be", "").replace("-", " ").title()
                maps_query = f"https://www.google.com/maps/search/{r['domain'].replace('.nl', '').replace('.be', '')}"
                gtm_str = ", ".join(r["gtm"]) if r["gtm"] else "None"
                kvk_str = ", ".join(r["kvk"]) if r["kvk"] else "Unregistered"
                claims_str = "; ".join(r["deceptive_claims"]) if r["deceptive_claims"] else "Leadgen portal front"

                writer.writerow({
                    "Business Name on Profile": name_clean,
                    "Google Maps URL": maps_query,
                    "Reported Address": "Netherlands (National / Virtual Dispatch)",
                    "Actual Occupant / True Business": f"{syndicate_name} - Affiliate Leadgen Front",
                    "KvK Commercial Registry Status": f"KvK: {kvk_str}",
                    "Specific Policy Violation Details": (
                        f"Ineligible lead-generation portal ({r['domain']}). GTM: {gtm_str}. "
                        f"Violations: {claims_str}. Violates Google Ineligible Businesses Guidelines."
                    )
                })

        return csv_path
