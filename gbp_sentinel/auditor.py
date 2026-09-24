"""Policy and fraud audit engine for Google Business Profiles."""

import json
import re
from . import config
from .spam_scorer import GbpSpamScorer

class GbpAuditor:
    def __init__(self):
        self.virtual_keywords = []
        self.virtual_addresses = []
        self.parcel_chains = []
        self.scorer = GbpSpamScorer()
        self._load_reference_data()

    def _load_reference_data(self):
        if config.VIRTUAL_OFFICES_PATH.exists():
            try:
                with open(config.VIRTUAL_OFFICES_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.virtual_keywords = [k.lower() for k in data.get("keywords", [])]
                    self.virtual_addresses = [a.lower() for a in data.get("known_addresses", [])]
            except Exception:
                pass

        if config.PARCEL_CHAINS_PATH.exists():
            try:
                with open(config.PARCEL_CHAINS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.parcel_chains = [c.lower() for c in data.get("chains", [])]
            except Exception:
                pass

    def audit_location(self, loc: dict, target_hq: str = "", target_kvk: str = "") -> dict:
        """Audit a single profile location for Google Business Profile policy violations."""
        name = loc.get("name", "")
        address = loc.get("address", "")
        snippet = loc.get("snippet", "")
        full_text = f"{name} {address} {snippet}".lower()

        evidence = []
        violation_category = "clean"
        actual_occupant = loc.get("actual_occupant", "Unverified Business Location")
        kvk_status = loc.get("kvk_status", "")
        violation_details = ""

        # Check if legitimate HQ
        if target_hq and target_hq.lower() in address.lower():
            return {
                **loc,
                "is_fraud": False,
                "is_reportable": False,
                "review_status": "clean",
                "evidence_signals": [],
                "violation_category": "headquarters",
                "actual_occupant": f"Official Registered Headquarters ({target_hq})",
                "kvk_status": f"Legally Registered (KvK: {target_kvk})",
                "violation_details": "None (Legitimate headquarters location)"
            }

        # 1. Check Virtual Office / Coworking
        matched_vo_kw = next((kw for kw in self.virtual_keywords if kw in full_text), None)
        matched_vo_addr = next((va for va in self.virtual_addresses if va in address.lower()), None)

        if matched_vo_kw or matched_vo_addr:
            evidence.append("known_virtual_office")
            violation_category = "virtual_office"
            matched_name = (matched_vo_kw or matched_vo_addr).title()
            actual_occupant = f"{matched_name} (Coworking Space & Virtual Office Provider)"
            violation_details = (
                f"Ineligible virtual office / coworking space ({matched_name}). "
                "Google guidelines require permanent, dedicated on-site staff during stated business hours. "
                "No trade staff or physical workshop present."
            )

        # 2. Check Parcel / Drop-off Partner
        matched_parcel = next((c for c in self.parcel_chains if c in full_text), None)
        if matched_parcel:
            evidence.append("parcel_or_partner_location")
            violation_category = "parcel_dropoff"
            actual_occupant = f"{matched_parcel.title()} (Third-Party Retail & Parcel Shop)"
            violation_details = (
                "Ineligible drop-off partner. Independent retail shop used as an unstaffed parcel point; "
                "falsely published as a dedicated trade or repair facility without permanent on-site staff."
            )

        # 3. Check Residential Address
        if any(term in full_text for term in ["woonadres", "residential", "appartement", "woning"]):
            evidence.append("residential_address_indicator")
            violation_category = "residential"
            actual_occupant = "Private Residential Home"
            violation_details = (
                "Residential address with public storefront display violating Google Service Area Business rules. "
                "Physical address must be hidden if customers are not served at this private home."
            )

        # 4. Check Keyword Stuffing in Title
        has_delimiter = any(d in name for d in ["|", " - ", " – ", " — ", ":"])
        if has_delimiter and not evidence:
            evidence.append("possible_keyword_stuffing")
            violation_category = "keyword_stuffing"
            actual_occupant = "Trade Contractor (Location Unverified)"
            violation_details = (
                "Keyword stuffed business title violating Google representation guidelines. "
                "Target geographic terms and trade keywords artificially injected into profile name."
            )

        # A single weak signal is useful for triage, but is not sufficient to
        # describe a listing as fraudulent or to include it in a complaint.
        strong_signals = {"known_virtual_office", "parcel_or_partner_location"}
        is_reportable = bool(strong_signals.intersection(evidence))
        is_fraud = is_reportable
        if not is_reportable and evidence:
            violation_category = "needs_review"
            violation_details = (
                "Potential policy concern found; verify the physical business presence "
                "and the profile name before reporting."
            )

        # Set KvK status
        if not kvk_status:
            if target_kvk:
                if target_hq and target_hq.lower() in address.lower():
                    kvk_status = f"Legally Registered (KvK: {target_kvk})"
                else:
                    kvk_status = f"Not registered at this address (KvK {target_kvk} registered at {target_hq or 'HQ'})"
            else:
                kvk_status = "No commercial registration at this address"

        return {
            **loc,
            "is_fraud": is_fraud,
            "is_reportable": is_reportable,
            "review_status": "ready_for_review" if is_reportable else ("needs_evidence" if evidence else "clean"),
            "evidence_signals": evidence,
            "violation_category": violation_category,
            "actual_occupant": actual_occupant,
            "kvk_status": kvk_status,
            "violation_details": violation_details
        }

    def audit_locations(self, locations: list, target_hq: str = "", target_kvk: str = "") -> list:
        """Audit a list of locations and return enriched results."""
        return [self.audit_location(loc, target_hq, target_kvk) for loc in locations]
