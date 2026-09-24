"""Discovery Engine for GBP SMOKER / Sentinel.

Allows researchers to explore a target area and niche for potential Google Business Profiles.
Preserves required fields:
- google_maps_url
- place_identifier
- business_name
- address
- phone
- website
- category
- rating
- review_count
- coordinates
- service_area
- description
- opening_hours
- source_timestamp

Missing values are explicitly stored as 'unknown' (never fabricated).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import config, db_v2, normalizer

logger = logging.getLogger(__name__)

UNKNOWN = "unknown"


class DiscoveryEngine:
    """Explores niches and locations, collects GBP profiles and ingests them into Sentinel v2."""

    REQUIRED_FIELDS = (
        "google_maps_url",
        "place_identifier",
        "business_name",
        "address",
        "phone",
        "website",
        "category",
        "rating",
        "review_count",
        "coordinates",
        "service_area",
        "description",
        "opening_hours",
        "source_timestamp",
    )

    def __init__(
        self,
        location: str,
        radius_km: float = 25.0,
        search_terms: Optional[Sequence[str]] = None,
        categories: Optional[Sequence[str]] = None,
        language: str = "nl",
        country: str = "NL",
        max_results: int = 50,
        db_path: Optional[str] = None,
    ) -> None:
        self.location = str(location).strip()
        self.radius_km = float(radius_km)
        self.search_terms = list(search_terms or ["slotenmaker", "loodgieter"])
        self.categories = list(categories or [])
        self.language = language
        self.country = country
        self.max_results = int(max_results)
        self.db_path = str(db_path or (config.DATA_DIR / "sentinel_v2.db"))

    def build_search_queries(self) -> List[str]:
        """Combine location, terms and categories into targeted search queries."""
        queries = []
        for term in self.search_terms:
            queries.append(f"{term} {self.location}".strip())
        for cat in self.categories:
            if cat not in self.search_terms:
                queries.append(f"{cat} {self.location}".strip())
        return queries

    def format_profile(self, raw: Mapping[str, Any]) -> Dict[str, Any]:
        """Format raw profile ensuring all required fields are present or set to 'unknown'."""
        now_ts = datetime.now(timezone.utc).isoformat()
        profile: Dict[str, Any] = {}

        profile["google_maps_url"] = str(raw.get("google_maps_url") or raw.get("url") or UNKNOWN)
        profile["place_identifier"] = str(raw.get("place_identifier") or raw.get("place_id") or raw.get("cid") or UNKNOWN)
        profile["business_name"] = str(raw.get("business_name") or raw.get("name") or raw.get("title") or UNKNOWN)
        profile["address"] = str(raw.get("address") or raw.get("formatted_address") or UNKNOWN)
        profile["phone"] = str(raw.get("phone") or raw.get("telephone") or UNKNOWN)
        profile["website"] = str(raw.get("website") or raw.get("domain") or UNKNOWN)
        profile["category"] = str(raw.get("category") or raw.get("types") or UNKNOWN)
        
        rating = raw.get("rating")
        profile["rating"] = str(rating) if rating is not None and rating != "" else UNKNOWN
        
        rev_count = raw.get("review_count") or raw.get("reviews") or raw.get("user_ratings_total")
        profile["review_count"] = str(rev_count) if rev_count is not None and rev_count != "" else UNKNOWN
        
        coords = raw.get("coordinates") or raw.get("location")
        if isinstance(coords, (dict, list, tuple)):
            profile["coordinates"] = json.dumps(coords)
        elif coords and str(coords).lower() != "none":
            profile["coordinates"] = str(coords)
        else:
            profile["coordinates"] = UNKNOWN

        profile["service_area"] = str(raw.get("service_area") or UNKNOWN)
        profile["description"] = str(raw.get("description") or raw.get("snippet") or UNKNOWN)
        profile["opening_hours"] = str(raw.get("opening_hours") or UNKNOWN)
        profile["source_timestamp"] = str(raw.get("source_timestamp") or now_ts)

        # Enforce no None or empty string
        for k in self.REQUIRED_FIELDS:
            if not profile.get(k) or profile[k] == "None":
                profile[k] = UNKNOWN

        return profile

    def ingest_to_db(self, profiles: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
        """Ingest profiles into Sentinel v2 relational database with normalization."""
        inserted_biz = 0
        updated_biz = 0
        snapshots_created = 0

        for raw in profiles:
            p = self.format_profile(raw)
            if p["business_name"] == UNKNOWN:
                continue

            # Normalization
            norm_phone = normalizer.normalize_phone(p["phone"]) if p["phone"] != UNKNOWN else None
            phone_prefix = normalizer.extract_phone_prefix(norm_phone) if norm_phone else None
            clean_name = normalizer.normalize_business_name(p["business_name"])
            clean_domain = normalizer.extract_domain(p["website"]) if p["website"] != UNKNOWN else None
            postal_code = normalizer.extract_postal_code(p["address"]) if p["address"] != UNKNOWN else None
            city = normalizer.extract_city(p["address"]) if p["address"] != UNKNOWN else self.location

            existing = None
            if p["place_identifier"] != UNKNOWN:
                existing = db_v2.get_by("businesses", "place_id", p["place_identifier"], db_path=self.db_path)
            if not existing and clean_name and p["address"] != UNKNOWN:
                existing = db_v2.get_by("businesses", "name", p["business_name"], db_path=self.db_path)

            now_iso = datetime.now(timezone.utc).isoformat()
            if existing:
                biz_id = existing["id"]
                db_v2.update(
                    "businesses",
                    biz_id,
                    {
                        "updated_at": now_iso,
                        "address": p["address"] if p["address"] != UNKNOWN else existing["address"],
                        "phone": p["phone"] if p["phone"] != UNKNOWN else existing["phone"],
                        "website": p["website"] if p["website"] != UNKNOWN else existing["website"],
                    },
                    db_path=self.db_path,
                )
                updated_biz += 1
            else:
                biz_id = db_v2.insert(
                    "businesses",
                    {
                        "place_id": p["place_identifier"] if p["place_identifier"] != UNKNOWN else None,
                        "name": p["business_name"],
                        "clean_name": clean_name,
                        "address": p["address"] if p["address"] != UNKNOWN else None,
                        "postal_code": postal_code,
                        "city": city,
                        "phone": p["phone"] if p["phone"] != UNKNOWN else None,
                        "normalized_phone": norm_phone,
                        "phone_prefix": phone_prefix,
                        "website": p["website"] if p["website"] != UNKNOWN else None,
                        "domain": clean_domain,
                        "status": "discovered",
                        "suspicion_score": 0,
                        "created_at": now_iso,
                        "updated_at": now_iso,
                    },
                    db_path=self.db_path,
                )
                inserted_biz += 1

            # Snapshot recording
            db_v2.insert(
                "business_snapshots",
                {
                    "business_id": biz_id,
                    "name": p["business_name"],
                    "address": p["address"],
                    "phone": p["phone"],
                    "website": p["website"],
                    "category": p["category"],
                    "rating": float(p["rating"]) if p["rating"] != UNKNOWN and p["rating"].replace(".", "", 1).isdigit() else None,
                    "review_count": int(p["review_count"]) if p["review_count"] != UNKNOWN and p["review_count"].isdigit() else None,
                    "service_area": p["service_area"],
                    "description": p["description"],
                    "opening_hours": p["opening_hours"],
                    "raw_payload_json": json.dumps(p),
                    "snapshot_timestamp": p["source_timestamp"],
                },
                db_path=self.db_path,
            )
            snapshots_created += 1

        return {
            "inserted_businesses": inserted_biz,
            "updated_businesses": updated_biz,
            "snapshots_created": snapshots_created,
        }
