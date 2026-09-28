from __future__ import annotations

import re
import unicodedata
from typing import Any
from urllib.parse import urlsplit


class NameSanitizer:
    """
    Intelligente naamsanering voor Google Bedrijfsprofielen.
    Identificeert keyword stuffing en extraheert de officiële handelsnaam.
    """

    def __init__(self):
        # Scheidingstekens die vaak worden gebruikt voor keyword stuffing
        self.delimiter_pattern = re.compile(r"\s*(?:\||--?|–|—|/|:|\b-\b|•|·|\+)\s*")

        # Niche-diensten die ten onrechte in titels worden geplakt
        self.service_keywords = {
            # Webdesign en IT
            "website laten maken", "webdesign", "webdesigner", "internetbureau",
            "online marketing", "seo bureau", "seo specialist", "webshop laten maken",
            "wordpress website", "applicatie ontwikkeling",
            # Bouw en onderhoud
            "gevelrenovatie", "gevelreiniging", "bouwbedrijf", "aannemer",
            "dakdekker", "dakrenovatie", "daklekkage", "dakbedekking", "bitumen dak",
            "loodgieter", "installatiebedrijf", "cv ketel", "warmtepomp",
            "schilder", "schildersbedrijf", "binnenschilder", "buitenschilder",
            "stukadoor", "stucadoor", "pleisterwerk", "spuitwerk",
            "vochtbestrijding", "kelderafdichting", "kruipruimte isolatie",
            "spouwmuurisolatie", "isolatiebedrijf",
            # Spoeddiensten
            "slotenmaker", "buitengesloten", "sleutelservice", "slot vervangen",
            "ontstoppingsbedrijf", "riool ontstoppen", "rioolreiniging", "afvoer ontstoppen",
            "ongediertebestrijding", "wespennest verwijderen", "muizen bestrijden",
            "elektricien", "storingsdienst", "stroomstoring", "groepenkast vervangen",
            # Automotive
            "autobanden", "bandenservice", "banden", "apk", "auto onderhoud",
            "garage", "autobedrijf", "autoverhuur", "auto huren", "occasions",
            "mobiele bandenservice", "autoinkoop", "auto verkopen",
            # Verzorging en beauty
            "nagelstudio", "biab nagels", "nagelstyliste", "manicure", "pedicure",
            "kapper", "barbier", "kapsalon", "hairstudio", "barbershop",
            "schoonheidssalon", "gezichtsbehandeling", "laser ontharen", "massage",
            # Transport en overig
            "verhuisbedrijf", "verhuizers", "transportbedrijf", "witgoed reparatie",
            "wasmachine reparatie", "fietsenmaker", "fietsenwinkel", "fietsreparatie"
        }

        # Nederlandse steden en regio's die vaak worden toegevoegd
        self.cities = {
            "amsterdam", "rotterdam", "den haag", "utrecht", "eindhoven", "almere",
            "tilburg", "breda", "groningen", "nijmegen", "arnhem", "haarlem",
            "amersfoort", "zaandam", "zoetermeer", "dordrecht", "leiden", "maastricht",
            "zwolle", "delft", "deventer", "alkmaar", "venlo", "leeuwarden",
            "helmond", "hilversum", "amstelveen", "oss", "roosendaal", "schiedam",
            "spijkenisse", "vlissingen", "gouda", "alphen aan den rijn", "hoofddorp",
            "scheveningen", "leidsche rijn", "osdorp", "sloterdijk", "zuid", "noord",
            "oost", "west", "centrum"
        }

        # Marketing buzzwords en claims
        self.marketing_buzzwords = {
            "specialist", "specialisten", "expert", "experts", "professioneel",
            "professionele", "goedkoop", "goedkope", "voordelig", "voordelige",
            "beste", "uw partner", "uw vakman", "spoed", "24/7", "24 7", "dag en nacht",
            "direct", "aan huis", "op locatie", "erkend", "gecertificeerd",
            "ervaren", "kwaliteit", "service", "totaalservice", "snel", "snelle"
        }

    def _clean_segment(self, segment: str) -> str:
        """Schoont overtollige tekens en leestekens op van een tekstsegment."""
        s = unicodedata.normalize("NFKC", segment)
        s = re.sub(r"[^\w\s&'.-]", " ", s)
        s = re.sub(r"\s+", " ", s)
        return s.strip(" \t\r\n,;|:-/.")

    def _is_service_or_location_segment(self, segment: str) -> bool:
        """Controleert of een segment hoofdzakelijk uit zoekwoorden, steden of claims bestaat."""
        lower = segment.lower().strip()
        
        # Exact match op bekende service of stad
        if lower in self.service_keywords or lower in self.cities:
            return True

        words = lower.split()
        if not words:
            return True

        matched_words = 0
        for w in words:
            w_clean = re.sub(r"[^\w]", "", w)
            if (
                w_clean in self.cities or 
                w_clean in self.marketing_buzzwords or 
                any(kw in lower for kw in ["specialist", "expert", "reparatie", "onderhoud", "laten maken", "spoed", "service"])
            ):
                matched_words += 1

        # Als meer dan 50% van de woorden in het segment zoekwoorden zijn
        return (matched_words / len(words)) >= 0.5

    def _extract_brand_from_domain(self, website_url: str) -> str:
        """Probeert de merknaam af te leiden uit het domein."""
        if not website_url:
            return ""
        try:
            parsed = urlsplit(website_url if "://" in website_url else f"https://{website_url}")
            host = (parsed.hostname or "").lower()
            if host.startswith("www."):
                host = host[4:]
            parts = host.split(".")
            if len(parts) >= 2:
                name_part = parts[0]
                # Filter generieke zoekwoorddomeinen eruit
                if any(kw.replace(" ", "") in name_part for kw in ["websitelatenmaken", "dakdekker", "slotenmaker", "loodgieter"]):
                    return ""
                return name_part.capitalize()
        except Exception:
            pass
        return ""

    def sanitize(self, raw_title: str, website_url: str = None, address: str = None) -> dict[str, Any]:
        """
        Analyseert een Google Bedrijfsprofiel titel en bepaalt de juiste actie en gesaneerde naam.
        
        Retourneert een dict met:
        - action: 'RENAME' (echt bedrijf met zoekwoorden) of 'REMOVE' (100% zoekwoord/spookprofiel)
        - clean_name: De geverifieerde gesaneerde naam
        - original_name: De oorspronkelijke titel
        - removed_parts: Lijst van verwijderde aanhangsels
        - confidence: Betrouwbaarheidsscore (0-100)
        - reasons: Uitleg van de uitgevoerde bewerking
        """
        raw = (raw_title or "").strip()
        if not raw:
            return {
                "action": "IGNORE",
                "clean_name": "",
                "original_name": raw,
                "removed_parts": [],
                "confidence": 0,
                "reasons": ["Lege titel opgegeven"]
            }

        reasons = []
        removed_parts = []

        # Stap 1: Controleer op 100% generieke zoektermen (zonder enige merknaam)
        lower_raw = raw.lower()
        clean_raw_no_space = re.sub(r"[^\w]", "", lower_raw)
        
        is_pure_query = (
            lower_raw in self.service_keywords or
            any(lower_raw == f"{svc} {city}" for svc in self.service_keywords for city in self.cities) or
            any(lower_raw == f"{svc} in {city}" for svc in self.service_keywords for city in self.cities) or
            clean_raw_no_space.startswith("123websitelatenmaken") or
            clean_raw_no_space.startswith("leadgenwebsite") or
            lower_raw in ["website maken", "website laten maken", "webdesign den haag", "webdesign eindhoven"]
        )

        if is_pure_query:
            return {
                "action": "REMOVE",
                "clean_name": "",
                "original_name": raw,
                "removed_parts": [raw],
                "confidence": 95,
                "reasons": ["Profielnaam bestaat voor 100% uit een generieke zoekterm zonder geregistreerde handelsnaam (Exact Match Spam). Verwijdering vereist."]
            }

        # Stap 2: Splitsen op scheidingstekens (| - / : enzovoort)
        segments = self.delimiter_pattern.split(raw)
        cleaned_segments = [self._clean_segment(s) for s in segments if s.strip()]

        if len(cleaned_segments) > 1:
            reasons.append(f"Scheidingstekens gedetecteerd met {len(cleaned_segments)} segmenten")
            
            candidate_brands = []
            for seg in cleaned_segments:
                if self._is_service_or_location_segment(seg):
                    removed_parts.append(seg)
                else:
                    candidate_brands.append(seg)

            if candidate_brands:
                # Kies het beste merksegment (meestal het segment met de hoogste eigennaam-waarde)
                chosen_brand = candidate_brands[0]
                # Als er meerdere overblijven, kies diegene die het minst op een dienst lijkt
                for cand in candidate_brands:
                    if any(w in cand.lower() for w in ["b.v.", "bv", "studio", "salon", "groep", "nederland", "holland"]):
                        chosen_brand = cand
                        break
                
                # Strip eventuele resterende steden of zoekwoorden aan het einde
                for city in self.cities:
                    chosen_brand = re.sub(rf"\b{city}\b", "", chosen_brand, flags=re.IGNORECASE).strip()
                
                # Schoon dubbele spaties op
                chosen_brand = re.sub(r"\s+", " ", chosen_brand).strip(" -|:,.")
                
                return {
                    "action": "RENAME",
                    "clean_name": chosen_brand,
                    "original_name": raw,
                    "removed_parts": removed_parts,
                    "confidence": 90,
                    "reasons": reasons + [f"Zoekwoorden gestript: {', '.join(removed_parts)}"]
                }

        # Stap 3: Geen scheidingstekens, maar wel aanhangsels (bv. 'KwikFit Amsterdam' of 'Salon New Age ✂')
        clean_name = raw
        # Verwijder niet-standaard symbolen en emoji's
        clean_name = re.sub(r"[✂🔑💧🚗🔨]+", "", clean_name).strip()

        # Controleer op achtervoegsels zoals 'Specialist in ...' of '- Autobanden, APK en onderhoud'
        tail_match = re.search(r"[-–|:]\s*(.+)$", clean_name)
        if tail_match:
            tail = tail_match.group(1).strip()
            if self._is_service_or_location_segment(tail):
                removed_parts.append(tail)
                clean_name = clean_name[:tail_match.start()].strip()
                reasons.append(f"Dienstaanhangsel verwijderd: '{tail}'")

        if removed_parts:
            return {
                "action": "RENAME",
                "clean_name": clean_name,
                "original_name": raw,
                "removed_parts": removed_parts,
                "confidence": 85,
                "reasons": reasons
            }

        # Geen duidelijke keyword stuffing gevonden
        return {
            "action": "KEEP",
            "clean_name": raw,
            "original_name": raw,
            "removed_parts": [],
            "confidence": 80,
            "reasons": ["Geen aantoonbare keyword stuffing of scheidingstekens aangetroffen"]
        }
