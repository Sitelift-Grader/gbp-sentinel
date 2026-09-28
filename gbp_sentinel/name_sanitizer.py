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
            "wordpress website", "applicatie ontwikkeling", "website bouwen",
            "website onderhoud", "webhosting", "domeinnaam", "ict",
            # Bouw en onderhoud
            "gevelrenovatie", "gevelreiniging", "bouwbedrijf", "aannemer",
            "dakdekker", "dakrenovatie", "daklekkage", "dakbedekking", "bitumen dak",
            "loodgieter", "installatiebedrijf", "cv ketel", "warmtepomp",
            "schilder", "schildersbedrijf", "binnenschilder", "buitenschilder",
            "stukadoor", "stucadoor", "pleisterwerk", "spuitwerk",
            "vochtbestrijding", "kelderafdichting", "kruipruimte isolatie",
            "spouwmuurisolatie", "isolatiebedrijf", "dakisolatie", "vloerisolatie",
            "glaszetter", "kozijnen", "kozijn vervangen", "deur vervangen",
            "betonboring", "sloopwerk", "verbouwing", "renovatie",
            # Spoeddiensten
            "slotenmaker", "buitengesloten", "sleutelservice", "slot vervangen",
            "ontstoppingsbedrijf", "riool ontstoppen", "rioolreiniging", "afvoer ontstoppen",
            "ongediertebestrijding", "wespennest verwijderen", "muizen bestrijden",
            "elektricien", "storingsdienst", "stroomstoring", "groepenkast vervangen",
            "loodgieter spoed", "daklekkage spoed", "kapotte cv",
            # Automotive
            "autobanden", "bandenservice", "banden", "apk", "auto onderhoud",
            "garage", "autobedrijf", "autoverhuur", "auto huren", "occasions",
            "mobiele bandenservice", "autoinkoop", "auto verkopen", "autoschade",
            "autopoetsbedrijf", "carwash", "wasstraat",
            # Verzorging en beauty
            "nagelstudio", "biab nagels", "nagelstyliste", "nagelstylist", "opleiding nagelstylist",
            "manicure", "pedicure", "kapper", "barbier", "kapsalon", "hairstudio", "barbershop",
            "schoonheidssalon", "gezichtsbehandeling", "laser ontharen", "massage",
            "visagie", "make-up", "wimperextensions", "waxstudio", "zonnebank",
            # Schoonmaak en facilitaire diensten
            "schoonmaakbedrijf", "schoonmaak", "glazenwasser", "glazenwasserij",
            "facilitaire diensten", "interieurverzorging", "eindschoonmaak",
            "bouwschoonmaak", "vloeren reinigen", "tapijtreiniging",
            # Tuin en buitenruimte
            "hovenier", "tuinonderhoud", "tuinaanleg", "bestrating", "grondverzet",
            "bomen snoeien", "boomverzorging", "grasmaaien", "tuindesign",
            # Beveiliging
            "beveiliging", "beveiligingsbedrijf", "camerabewaking", "alarminstallatie",
            "brandbeveiliging", "brandmeldinstallatie", "toegangscontrole",
            # Overig
            "verhuisbedrijf", "verhuizers", "transportbedrijf", "witgoed reparatie",
            "wasmachine reparatie", "fietsenmaker", "fietsenwinkel", "fietsreparatie",
            "drukkerij", "drukwerk", "reclamebureau", "signmaking",
            "schoorsteenveger", "rioolinspectie", "fundering", "onderhoudsbedrijf"
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
            "oost", "west", "centrum", "den bosch", "apeldoorn", "enschede",
            "haarlemmermeer", "purmerend", "hoorn", "alkmaar", "bergen op zoom",
            "middelburg", "sittard", "heerlen", "kerkrade", "brunssum", "venray",
            "weert", "roermond", "tilburg", "breda", "eindhoven", "helmond",
            "oss", "uden", "veghel", "cuijk", "grave", "boxmeer", "gemert",
            "boxtel", "oisterwijk", "gilze", "rijen", "goirle", "hilvarenbeek",
            "best", "son", "nuenen", "geldrop", "mierlo", "valkenswaard",
            "eersel", "bladel", "reusel", "bergeijk", "asten", "someren",
            "deurne", "horst", "sevenum", "helenaveen", "griendtsveen",
            "amsterdam zuidoost", "amsterdam noord", "amsterdam west",
            "utrecht zuid", "utrecht oost", "utrecht west", "utrecht noord",
            "den haag zuid", "den haag noord", "rotterdam zuid", "rotterdam noord",
            "rotterdam west", "rotterdam oost", "eindhoven noord", "eindhoven zuid",
            "tilburg noord", "tilburg zuid", "breda noord", "breda zuid",
            "groningen noord", "groningen zuid", "nijmegen noord", "nijmegen zuid",
            "arnhem noord", "arnhem zuid", "haarlem noord", "haarlem zuid",
            "leiden noord", "leiden zuid", "maastricht noord", "maastricht zuid"
        }

        # Marketing buzzwords en claims
        self.marketing_buzzwords = {
            "specialist", "specialisten", "expert", "experts", "professioneel",
            "professionele", "goedkoop", "goedkope", "voordelig", "voordelige",
            "beste", "uw partner", "uw vakman", "spoed", "24/7", "24 7", "dag en nacht",
            "direct", "aan huis", "op locatie", "erkend", "gecertificeerd",
            "ervaren", "kwaliteit", "service", "totaalservice", "snel", "snelle",
            "top", "beste", "goed", "voordelig", "scherp", "laagste prijs",
            "garantie", "inclusief", "gratis", "actie", "aanbieding", "deal"
        }

        # Extraheer individuele service-woorden voor snelle token-lookup
        self.single_service_tokens = set()
        for kw in self.service_keywords:
            for w in kw.split():
                if len(w) > 3:
                    self.single_service_tokens.add(w)
        self.single_service_tokens.update({
            "nagelstylist", "nagelstyliste", "opleiding", "cursus", "workshop",
            "nagelstudio", "beauty", "salon", "kapper", "barbier", "onderhoud",
            "reparatie", "spoedservice", "sleutel", "dakdekker", "gevel",
            "schoonmaak", "hovenier", "beveiliging", "installatie", "montage",
            "reiniging", "renovatie", "verbouwing", "isolatie", "verwarming",
            "elektra", "loodgieter", "cv", "ketel", "dak", "kozijn", "raam"
        })

        # Woorden die vaak in merknamen voorkomen en nooit als spam worden gezien
        self.brand_indicators = {
            "b.v.", "bv", "vof", "holding", "group", "groep", "nederland", "holland",
            "studio", "salon", "shop", "store", "company", "bedrijf", "onderneming",
            "concept", "design", "creations", "works", "pro", "plus", "center", "centrum"
        }

        # Preposities die vaak in adressen/zoektermen voorkomen
        self.prepositions = {"in", "te", "op", "voor", "bij", "aan", "met", "en", "van", "de", "het", "een", "der"}

    def _clean_segment(self, segment: str) -> str:
        """Schoont overtollige tekens en leestekens op van een tekstsegment."""
        s = unicodedata.normalize("NFKC", segment)
        s = re.sub(r"[^\w\s&'.-]", " ", s)
        s = re.sub(r"\s+", " ", s)
        return s.strip(" \t\r\n,;|:-/.")

    def _is_service_or_location_segment(self, segment: str) -> bool:
        """Controleert of een segment hoofdzakelijk uit zoekwoorden, steden of claims bestaat."""
        lower = segment.lower().strip()
        if not lower:
            return True

        # Exact match op bekende service of stad
        if lower in self.service_keywords or lower in self.cities:
            return True

        # Controleer of het segment een stad bevat (als deel van de naam)
        for city in self.cities:
            if city in lower:
                # Als de stad het grootste deel is, is het een locatiesegment
                city_len = len(city)
                if city_len / len(lower) > 0.5:
                    return True

        words = [re.sub(r"[^\w]", "", w) for w in lower.split()]
        words = [w for w in words if w and w not in self.prepositions]
        if not words:
            return True

        matched_words = 0
        for w in words:
            if (
                w in self.cities or 
                w in self.marketing_buzzwords or 
                w in self.single_service_tokens or
                any(kw in w for kw in ["specialist", "expert", "reparatie", "onderhoud", "laten", "maken", "spoed", "service", "nagel", "dak", "slot", "gevel", "schoonmaak", "hovenier", "beveiliging", "installatie"])
            ):
                matched_words += 1

        # Als minstens 50% van de betekenisvolle woorden zoekwoorden zijn
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
                generic_domains = ["websitelatenmaken", "dakdekker", "slotenmaker", "loodgieter", "schoonmaak", "hovenier", "beveiliging"]
                if any(kw in name_part for kw in generic_domains):
                    return ""
                # Verwijder eventuele cijfers of streepjes die geen merk zijn
                name_part = re.sub(r"^[0-9]+", "", name_part)
                name_part = re.sub(r"[-_]", "", name_part)
                return name_part
        except Exception:
            pass
        return ""

    def _looks_like_brand(self, segment: str) -> bool:
        """Controleert of een segment een echte merknaam kan zijn."""
        lower = segment.lower().strip()
        if not lower:
            return False
        # Heeft minimaal 2 letters
        if len(re.sub(r"[^\w]", "", lower)) < 2:
            return False
        # Bevat een merkindicator
        for indicator in self.brand_indicators:
            if indicator in lower:
                return True
        # Heeft hoofdletters (behalve als het een afkorting is)
        if any(c.isupper() for c in segment):
            return True
        # Alleen een woord dat geen service/locatie is
        if self._is_service_or_location_segment(segment):
            return False
        # Als het segment uit 1-2 woorden bestaat en geen bekende service/locatie is
        words = segment.split()
        if len(words) <= 2:
            return True
        # Anders twijfelachtig
        return False

    def sanitize(self, raw_title: str, website_url: str = None, address: str = None) -> dict[str, Any]:
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

        lower_raw = raw.lower()
        clean_raw_no_space = re.sub(r"[^\w]", "", lower_raw)
        
        # Pure zoekopdrachten (exact match spam)
        is_pure_query = (
            lower_raw in self.service_keywords or
            any(lower_raw == f"{svc} {city}" for svc in self.service_keywords for city in self.cities) or
            any(lower_raw == f"{svc} in {city}" for svc in self.service_keywords for city in self.cities) or
            clean_raw_no_space.startswith("123websitelatenmaken") or
            clean_raw_no_space.startswith("leadgenwebsite") or
            lower_raw in ["website maken", "website laten maken", "webdesign den haag", "webdesign eindhoven", "leadgen website den haag"] or
            re.fullmatch(r"[\d\s]+", raw) is not None
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

            if not candidate_brands:
                # Als alle segmenten als service werden gemarkeerd, is het puur spam
                return {
                    "action": "REMOVE",
                    "clean_name": "",
                    "original_name": raw,
                    "removed_parts": removed_parts,
                    "confidence": 95,
                    "reasons": ["Alle segmenten bestaan uit generieke zoekwoorden of locaties zonder merknaam"]
                }

            domain_brand = self._extract_brand_from_domain(website_url)

            # Kies het beste merksegment
            chosen_brand = candidate_brands[0]
            if len(candidate_brands) > 1:
                # Prioriteit 1: Domein match
                if domain_brand:
                    for cand in candidate_brands:
                        clean_cand = re.sub(r"[^\w]", "", cand.lower())
                        if domain_brand in clean_cand or clean_cand in domain_brand:
                            chosen_brand = cand
                            reasons.append(f"Merksegment geverifieerd via websitedomein: '{cand}'")
                            break
                # Prioriteit 2: Bevat entiteitsindicator
                if chosen_brand == candidate_brands[0]:
                    for cand in candidate_brands:
                        if any(w in cand.lower() for w in self.brand_indicators):
                            chosen_brand = cand
                            break
                # Prioriteit 3: Langste segment dat als merk lijkt
                if chosen_brand == candidate_brands[0]:
                    best_len = 0
                    for cand in candidate_brands:
                        if self._looks_like_brand(cand) and len(cand) > best_len:
                            best_len = len(cand)
                            chosen_brand = cand

            # Strip eventuele steden die nog in het gekozen segment hangen
            for city in self.cities:
                chosen_brand = re.sub(rf"\b{city}\b", "", chosen_brand, flags=re.IGNORECASE).strip()
            
            # Verwijder voorzetsels die overblijven
            for prep in self.prepositions:
                chosen_brand = re.sub(rf"\b{prep}\b", "", chosen_brand, flags=re.IGNORECASE).strip()

            chosen_brand = re.sub(r"\s+", " ", chosen_brand).strip(" -|:,.")

            # Als de uiteindelijke naam leeg is of te kort
            if len(chosen_brand) < 2:
                return {
                    "action": "REMOVE",
                    "clean_name": "",
                    "original_name": raw,
                    "removed_parts": removed_parts,
                    "confidence": 90,
                    "reasons": ["Na sanering resteert geen geldige handelsnaam"]
                }
            
            return {
                "action": "RENAME",
                "clean_name": chosen_brand,
                "original_name": raw,
                "removed_parts": removed_parts,
                "confidence": 90,
                "reasons": reasons + [f"Zoekwoorden gestript: {', '.join(removed_parts)}"]
            }

        # Geen scheidingstekens, check op aanhangsels
        clean_name = raw
        clean_name = re.sub(r"[✂🔑💧🚗🔨]+", "", clean_name).strip()

        # Verwijder staart zoals " - service" of " | Amsterdam"
        tail_match = re.search(r"[-–|:]\s*(.+)$", clean_name)
        if tail_match:
            tail = tail_match.group(1).strip()
            if self._is_service_or_location_segment(tail):
                removed_parts.append(tail)
                clean_name = clean_name[:tail_match.start()].strip()
                reasons.append(f"Dienstaanhangsel verwijderd: '{tail}'")

        # Strip stad aan einde indien niet de enige naam
        for city in self.cities:
            if clean_name.lower().endswith(f" {city}") and len(clean_name.split()) > 1:
                clean_name = clean_name[:-(len(city) + 1)].strip()
                removed_parts.append(city)
                reasons.append(f"Plaatsnaam gestript: '{city}'")

        # Verwijder eventuele achtergebleven voorzetsels aan het einde indien er aanhangsels zijn gestript
        if removed_parts:
            for prep in ["in", "te", "op", "voor", "bij", "aan"]:
                if clean_name.lower().endswith(f" {prep}"):
                    clean_name = clean_name[:-(len(prep)+1)].strip()

        # Verwijder dubbele spaties en leestekens aan randen
        clean_name = re.sub(r"\s+", " ", clean_name).strip(" -|:,.")

        if removed_parts:
            return {
                "action": "RENAME",
                "clean_name": clean_name,
                "original_name": raw,
                "removed_parts": removed_parts,
                "confidence": 85,
                "reasons": reasons
            }

        return {
            "action": "KEEP",
            "clean_name": raw,
            "original_name": raw,
            "removed_parts": [],
            "confidence": 80,
            "reasons": ["Geen aantoonbare keyword stuffing of scheidingstekens aangetroffen"]
        }
