"""Google Business Profile Spam & Abuse Scoring Engine.

Transforms subjective listing reviews into quantifiable, explainable
spam intelligence with granular keyword stuffing, flex hub, and VoIP network indicators.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


class GbpSpamScorer:
    """Evaluates individual Google Business Profiles for policy violations and network abuse."""

    DELIMITERS = ["|", " - ", " – ", " — ", ":", "/"]
    
    SPAM_MODIFIERS = [
        "24/7", "24 7", "spoed", "beste", "goedkoopste", "gratis", 
        "direct", "expert", "specialist", "no cure no pay", "gecertificeerd",
        "betaalbaar", "erkend", "kwaliteit", "binnen 30 min"
    ]
    
    VOIP_PBX_PATTERNS = ["369", "360", "569", "669", "798", "796", "794", "455", "754", "793"]
    NON_GEOGRAPHIC_PREFIXES = ["085", "088"]
    
    VIRTUAL_OFFICE_KEYWORDS = [
        "regus", "spaces", "wework", "tribes", "hNK", "flexoffiz", "business center",
        "flexplek", "virtueel kantoor", "postadres", "verzamelpand", "coworking"
    ]

    def calculate_keyword_stuffing_score(
        self, 
        name: str, 
        city: str = "", 
        category: str = ""
    ) -> Dict[str, Any]:
        """Analyze a listing title for unnatural keyword and location stuffing.
        
        Returns:
            dict containing numerical score (0-100), classification level, and specific triggers.
        """
        score = 0
        triggers: List[str] = []
        name_clean = name.strip()
        name_lower = name_clean.lower()

        # 1. Delimiter evaluation
        found_delims = [d for d in self.DELIMITERS if d in name_clean]
        if found_delims:
            delim_count = sum(name_clean.count(d) for d in found_delims)
            if delim_count >= 2:
                score += 35
                triggers.append(f"Meerdere zoekwoord-scheidingstekens gedetecteerd ({delim_count}x)")
            elif delim_count == 1:
                score += 15
                triggers.append("Zoekwoord-scheidingsteken in bedrijfsnaam aanwezig")

        # 2. Marketing modifiers & superlatives
        found_modifiers = [m for m in self.SPAM_MODIFIERS if re.search(r'\b' + re.escape(m) + r'\b', name_lower)]
        if found_modifiers:
            score += len(found_modifiers) * 20
            triggers.append(f"Niet-zakelijke marketingtermen in titel: {', '.join(found_modifiers)}")

        # 3. Location stuffing
        if city and city.lower() in name_lower:
            # Check if city is added as an artificial suffix or keyword
            base_name = re.sub(re.escape(city), '', name_clean, flags=re.IGNORECASE).strip(" -|:–—/")
            if len(base_name) >= 3:
                score += 25
                triggers.append(f"Plaatsnaam '{city.capitalize()}' kunstmatig aan bedrijfsnaam toegevoegd")

        # 4. Excessive word length
        words = re.findall(r'\b\w+\b', name_clean)
        if len(words) >= 6:
            score += 20
            triggers.append(f"Bovengemiddelde titellengte ({len(words)} woorden)")

        score = min(100, max(0, score))

        if score < 20:
            level = "clean"
        elif score < 50:
            level = "suspicious"
        elif score < 75:
            level = "highly_suspicious"
        else:
            level = "extreme"

        return {
            "score": score,
            "level": level,
            "triggers": triggers,
            "cleaned_brand_guess": base_name if (city and city.lower() in name_lower) else name_clean
        }

    def calculate_abuse_score(self, location_data: Dict[str, Any]) -> Dict[str, Any]:
        """Aggregate multiple independent risk indicators into a composite abuse score."""
        name = location_data.get("name", "")
        city = location_data.get("city", "")
        address = location_data.get("address", "").lower()
        phone = location_data.get("phone", "")
        actual_occupant = location_data.get("actual_occupant", "").lower()
        site_address = location_data.get("site_address", "").lower()

        evidence_points: List[str] = []
        score = 0

        # Component A: Keyword stuffing (0-30 pts)
        kw_res = self.calculate_keyword_stuffing_score(name, city=city)
        if kw_res["score"] > 0:
            kw_points = int(kw_res["score"] * 0.3)
            score += kw_points
            evidence_points.extend(kw_res["triggers"])

        # Component B: Virtual office / unstaffed flex hub (0-35 pts)
        is_flex = any(kw in address or kw in actual_occupant or kw in site_address for kw in self.VIRTUAL_OFFICE_KEYWORDS)
        if is_flex or "unstaffed" in actual_occupant:
            score += 35
            evidence_points.append(f"Geregistreerd op onbemand flexkantoor/verzamelgebouw ({location_data.get('actual_occupant') or 'Regus/Spaces'})")

        # Component C: Consecutive VoIP PBX signature (0-25 pts)
        digits = re.sub(r'\D', '', phone)
        has_voip_block = any(p in digits for p in self.VOIP_PBX_PATTERNS)
        has_non_geo = any(phone.strip().startswith(prefix) for prefix in self.NON_GEOGRAPHIC_PREFIXES)
        
        if has_voip_block:
            score += 25
            evidence_points.append(f"Gebruik van VoIP SIP-trunk blok passend bij syndicaat-reeks ({phone})")
        elif has_non_geo:
            score += 15
            evidence_points.append(f"Gebruik van landelijk 085/088 VoIP-servicenummer ({phone})")

        # Component D: Ghost entity / Trade Register mismatch (0-15 pts)
        kvk_status = str(location_data.get("kvk_status", "")).lower()
        if "unregistered" in kvk_status or "onbekend" in kvk_status or "ghost" in kvk_status:
            score += 15
            evidence_points.append("Geen geldige, traceerbare inschrijving in het Handelsregister (KvK)")

        # Component E: Multi-city cloning evidence
        if location_data.get("multi_city_clone") or location_data.get("network_cluster_size", 0) > 1:
            score += 15
            evidence_points.append(f"Onderdeel van gecorreleerd netwerk over {location_data.get('network_cluster_size', 'meerdere')} steden")

        overall_score = min(100, max(0, score))

        if overall_score >= 80:
            confidence = "CRITICAL"
        elif overall_score >= 55:
            confidence = "HIGH"
        elif overall_score >= 30:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        return {
            "overall_score": overall_score,
            "confidence": confidence,
            "evidence_points": evidence_points,
            "keyword_details": kw_res
        }
