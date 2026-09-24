from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping, MutableMapping, Sequence


__all__ = [
    "KeywordStuffingDetector",
    "VirtualOfficeDetector",
    "DuplicateDetector",
    "LeadGenDetector",
]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _fold(value: Any) -> str:
    value = unicodedata.normalize("NFKD", _text(value))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value).strip().casefold()


def _compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _fold(value))


def _tokens(value: Any) -> list[str]:
    return re.findall(r"[a-z0-9]+", _fold(value))


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(mapping: Mapping[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return default


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _confidence(score: int, signal_found: bool = True) -> str:
    if not signal_found:
        return "LOW"
    if score >= 75:
        return "HIGH"
    if score >= 45:
        return "MEDIUM"
    return "LOW"


def _similarity(left: Any, right: Any) -> float:
    left_value = _compact(left)
    right_value = _compact(right)
    if not left_value or not right_value:
        return 0.0
    return SequenceMatcher(None, left_value, right_value).ratio()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _fold(value) in {"1", "true", "yes", "y", "on"}


def _address(value: Any) -> str:
    if isinstance(value, Mapping):
        parts = [
            _first(value, "street", "address_line_1", "address1", "line1"),
            _first(value, "house_number", "number"),
            _first(value, "postal_code", "postcode", "zip"),
            _first(value, "city", "locality", "town"),
            _first(value, "country"),
        ]
        return " ".join(_text(part) for part in parts if _text(part))
    return _text(value)


def _normalised_address(value: Any) -> str:
    return _compact(_address(value))


def _phone(value: Any) -> str:
    return re.sub(r"\D+", "", _text(value))


def _domain(value: Any) -> str:
    raw = _text(value).casefold()
    raw = re.sub(r"^[a-z]+://", "", raw)
    raw = raw.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    raw = raw.split("@")[-1]
    if ":" in raw:
        raw = raw.split(":", 1)[0]
    if raw.startswith("www."):
        raw = raw[4:]
    return raw.strip(".")


def _is_service_business(listing: Mapping[str, Any]) -> bool:
    explicit = _first(
        listing,
        "business_type",
        "category",
        "primary_category",
        "service_type",
        default="",
    )
    if explicit:
        return any(
            term in _fold(explicit)
            for term in (
                "contractor",
                "plumber",
                "electrician",
                "roofer",
                "builder",
                "cleaning",
                "locksmith",
                "repair",
                "home service",
                "service area",
                "klus",
                "loodgieter",
                "elektricien",
                "schilder",
                "painter",
                "aannemer",
                "dakdekker",
                "slotenmaker",
            )
        )
    title = _first(listing, "title", "name", default="")
    if title:
        return any(
            term in _fold(title)
            for term in (
                "loodgieter", "plumber", "dakdekker", "roofer", "slotenmaker", "locksmith",
                "elektricien", "electrician", "schilder", "painter", "aannemer", "contractor"
            )
        )
    return _bool(_first(listing, "service_area_business", "sab", default=False))


@dataclass(frozen=True)
class KeywordStuffingDetector:
    cities: frozenset[str] = frozenset({
        "amsterdam", "rotterdam", "den haag", "the hague", "utrecht", "eindhoven",
        "almere", "tilburg", "groningen", "breda", "nijmegen", "arnhem", "haarlem",
        "zaanstad", "amersfoort", "apeldoorn", "enschede", "dordrecht", "leiden",
        "zoetermeer", "maastricht", "venlo", "deventer", "leeuwarden", "middelburg",
        "alkmaar", "den bosch", "s hertogenbosch", "'s-hertogenbosch", "purmerend",
        "hilversum", "hengelo", "oss", "spijkenisse", "ede", "emmen", "houten",
        "hoofddorp", "zwolle", "delft",
    })

    trade_modifiers: tuple[str, ...] = (
        "24/7", "24 7", "spoed", "goedkoopste", "beste", "no cure no pay",
        "binnen 30 min", "direct", "erkend", "gecertificeerd",
    )

    delimiters: tuple[str, ...] = (" | ", " - ", " – ", " — ", " : ", " / ")

    def detect(self, listing: Mapping[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        data: dict[str, Any] = dict(_as_mapping(listing))
        data.update(kwargs)

        title = _text(_first(data, "title", "business_title", "name"))
        clean_name = _text(_first(data, "clean_name", "brand_name", "canonical_name", "normalized_name"))
        legal_name = _text(_first(data, "website_legal_name", "legal_name", "website_name"))
        reference = clean_name or legal_name

        title_folded = _fold(title)
        reasons: list[str] = []
        score = 0
        found_cities: list[str] = []
        found_modifiers: list[str] = []
        found_delimiters: list[str] = []

        if reference:
            similarity = _similarity(title, reference)
            if similarity < 0.72:
                score += 30
                reasons.append("Business title differs materially from the verified brand/legal name.")
            elif similarity < 0.88:
                score += 15
                reasons.append("Business title contains extra descriptive modifiers beyond brand name.")

        for city in sorted(self.cities, key=len, reverse=True):
            if re.search(rf"(?<![a-z]){re.escape(city)}(?![a-z])", title_folded):
                found_cities.append(city)
        if found_cities:
            score += min(35, 15 + (len(found_cities) - 1) * 8)
            reasons.append(f"Business title contains geographic location terms: {', '.join(found_cities)}.")

        for modifier in self.trade_modifiers:
            if modifier in title_folded:
                found_modifiers.append(modifier)
        if found_modifiers:
            score += min(35, 15 + (len(found_modifiers) - 1) * 7)
            reasons.append(f"Business title contains promotional/urgency modifiers: {', '.join(found_modifiers)}.")

        for delimiter in self.delimiters:
            if delimiter in title:
                found_delimiters.append(delimiter)
        if found_delimiters:
            score += min(20, len(found_delimiters) * 8)
            reasons.append("Business title uses artificial keyword-delimiter punctuation.")

        clean_guess = reference
        if not clean_guess and title:
            clean_guess = re.split(r"\s+(?:\||-|–|—|:)\s+", title, maxsplit=1)[0].strip()
        if clean_guess and found_cities:
            pattern = r"\s*(?:,|\||-|–|—|:)?\s*(?:" + "|".join(re.escape(c) for c in found_cities) + r")\s*$"
            clean_guess = re.sub(pattern, "", clean_guess, flags=re.IGNORECASE).strip(" ,-–—:")

        score = max(0, min(100, score))
        signal = bool(found_cities or found_modifiers or found_delimiters or (reference and _similarity(title, reference) < 0.72))
        return {
            "signal_found": signal,
            "confidence": _confidence(score, signal),
            "score": score,
            "clean_brand_guess": clean_guess or title,
            "reasons": reasons if reasons else ["No material keyword-stuffing observation found."],
            "policy_id": "GBP-POL-NAME-01",
        }

    __call__ = detect


@dataclass(frozen=True)
class VirtualOfficeDetector:
    flex_office_chains: frozenset[str] = frozenset({
        "regus", "spaces", "tribes", "wework", "hnk", "the great room",
        "workthere", "sungate", "seats2meet", "verzamelgebouw", "microlab",
        "business center", "bedrijvencentrum", "flexoffiz", "kantoorverzamelgebouw",
    })
    known_virtual_addresses: frozenset[str] = frozenset({
        "hofplein 20", "zekeringstraat", "weena", "st jacobsstraat", "orteliuslaan",
        "databankweg", "flight forum", "teldersstraat", "jonkerbosplein", "mandelaplein",
        "verlengde poolseweg", "paterswoldseweg", "bargelaan",
    })

    def detect(self, listing: Mapping[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        data: dict[str, Any] = dict(_as_mapping(listing))
        data.update(kwargs)

        address = _address(_first(data, "address", "formatted_address", default=""))
        address_key = _normalised_address(address)
        address_text = _fold(address)
        title = _text(_first(data, "title", "business_title", "name"))
        reasons: list[str] = []
        score = 0
        hub_name = ""
        policy_id = "GBP-POL-VO-01"

        supplied_hub = _text(_first(data, "hub_name", "office_provider", "building_operator"))
        candidates = " ".join((_fold(title), address_text, _fold(supplied_hub), _fold(_first(data, "description", default=""))))
        
        for chain in sorted(self.flex_office_chains, key=len, reverse=True):
            if re.search(rf"(?<![a-z]){re.escape(chain)}(?![a-z])", candidates):
                hub_name = supplied_hub or chain.title()
                score += 55
                reasons.append(f"Address or listing references a known flexible-office provider: {hub_name}.")
                break

        for known_addr in self.known_virtual_addresses:
            if known_addr in address_text:
                score += 45
                reasons.append(f"Address matches known commercial business center / flex hub: {known_addr.title()}.")
                if not hub_name:
                    hub_name = known_addr.title()
                break

        address_type = _fold(_first(data, "address_type", "property_type", default=""))
        residential = _bool(_first(data, "residential", "is_residential", default=False)) or any(
            term in address_type for term in ("residential", "home", "woning", "appartement", "flat")
        )
        publicly_displayed = _bool(_first(data, "publicly_displayed", "address_public", "public_address", default=True))
        if residential and publicly_displayed and _is_service_business(data):
            score += 45
            policy_id = "GBP-POL-SAB-01"
            reasons.append("Residential address publicly displayed for a contractor / service-area business.")

        actual_occupant = _text(_first(data, "actual_occupant_guess", "occupant_name", default=""))
        if not actual_occupant and hub_name:
            actual_occupant = f"{hub_name} (Commercial Coworking & Business Center)"

        score = min(100, score)
        signal = score > 0
        return {
            "signal_found": signal,
            "confidence": _confidence(score, signal),
            "hub_name": hub_name,
            "actual_occupant_guess": actual_occupant or "Unverified Business Location",
            "reasons": reasons if reasons else ["No virtual-office or residential policy concern detected."],
            "policy_id": policy_id,
        }

    __call__ = detect


@dataclass(frozen=True)
class DuplicateDetector:
    def detect(
        self,
        listing: Mapping[str, Any] | None = None,
        candidates: Sequence[Mapping[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        current: dict[str, Any] = dict(_as_mapping(listing))
        current.update(kwargs)
        all_candidates = [dict(item) for item in (candidates or []) if isinstance(item, Mapping)]

        current_id = _text(_first(current, "listing_id", "profile_id", "id", "place_id", default=""))
        current_address = _normalised_address(_first(current, "address", "formatted_address", default=""))
        current_phone = _phone(_first(current, "phone", "telephone", "primary_phone", "normalized_phone", default=""))
        current_domain = _domain(_first(current, "domain", "website", "canonical_url", default=""))

        reasons: list[str] = []
        matches: list[Mapping[str, Any]] = []
        for candidate in all_candidates:
            candidate_id = _text(_first(candidate, "listing_id", "profile_id", "id", "place_id", default=""))
            if current_id and candidate_id and current_id == candidate_id:
                continue

            candidate_address = _normalised_address(_first(candidate, "address", "formatted_address", default=""))
            candidate_phone = _phone(_first(candidate, "phone", "telephone", "primary_phone", "normalized_phone", default=""))
            candidate_domain = _domain(_first(candidate, "domain", "website", "canonical_url", default=""))

            same_address = bool(current_address and candidate_address and current_address == candidate_address)
            same_phone = bool(current_phone and candidate_phone and current_phone == candidate_phone)
            same_domain = bool(current_domain and candidate_domain and current_domain == candidate_domain)

            is_official_branch = _bool(_first(candidate, "official_branch", "is_franchise", default=False)) or _bool(
                _first(current, "official_branch", "is_franchise", default=False)
            )
            distinct_address = bool(current_address and candidate_address and current_address != candidate_address)

            identity_matches = sum((same_address, same_phone, same_domain))
            # Legitimate multi-location businesses have different physical branch addresses
            if identity_matches >= 2 and not (is_official_branch and distinct_address):
                matches.append(candidate)
                if same_address:
                    reasons.append("Another profile shares the exact physical address.")
                if same_phone:
                    reasons.append("Another profile shares the primary phone number.")
                if same_domain:
                    reasons.append("Another profile shares the official website domain.")

        parts = [current_address, current_phone, current_domain]
        group_key = "|".join(part for part in parts if part)

        score = min(100, len(matches) * 30 + (25 if len(matches) >= 2 else 0))
        signal = bool(matches)
        return {
            "signal_found": signal,
            "confidence": _confidence(score, signal),
            "duplicate_group_key": group_key,
            "matches_count": len(matches),
            "reasons": _unique(reasons) if reasons else ["Distinct profile identity; no duplicate conflict observed."],
            "policy_id": "GBP-POL-DUP-01",
        }

    __call__ = detect


@dataclass(frozen=True)
class LeadGenDetector:
    city_domain_pattern: re.Pattern[str] = re.compile(
        r"(?P<trade>[a-z0-9-]{3,20})(?:[-_]?)(?P<city>amsterdam|rotterdam|denhaag|utrecht|eindhoven|almere|tilburg|groningen|breda|nijmegen|arnhem|haarlem|amersfoort|apeldoorn|enschede|dordrecht|leiden|zoetermeer|zwolle|delft)\.(?:nl|com|net)",
        re.IGNORECASE,
    )

    def detect(self, listing: Mapping[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        data: dict[str, Any] = dict(_as_mapping(listing))
        data.update(kwargs)

        domain = _domain(_first(data, "domain", "website", "canonical_url", default=""))
        phone = _text(_first(data, "normalized_phone", "phone", default=""))
        reasons: list[str] = []
        score = 0
        footprint_type = "STANDARD_LOCAL"

        # 1. Pattern matching on templated domains: {trade}{city}.(nl|com|net)
        m = self.city_domain_pattern.search(domain)
        if m:
            trade = m.group("trade")
            city = m.group("city")
            score += 45
            footprint_type = "TEMPLATED_GEO_DOMAIN"
            reasons.append(f"Domain follows geo-cloning template: trade '{trade}' combined with city '{city}'.")

        # 2. VoIP prefix central dispatch
        prefix = _text(_first(data, "phone_prefix", "pbx_prefix_6", default=""))
        if prefix and any(p in prefix for p in ("085", "088")):
            score += 25
            reasons.append("Uses non-geographic VoIP prefix (085/088) commonly associated with remote call centers.")

        score = min(100, score)
        signal = score >= 35
        return {
            "signal_found": signal,
            "confidence": _confidence(score, signal),
            "footprint_type": footprint_type,
            "reasons": reasons if reasons else ["Standard localized domain and contact pattern."],
            "policy_id": "GBP-POL-LEADGEN-01",
        }

    __call__ = detect
