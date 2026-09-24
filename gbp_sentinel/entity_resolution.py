"""Entity resolution engine for GBP SMOKER / Sentinel.

Detects multi-attribute pairwise linkages between Google Business Profiles:
- SAME_PHONE
- SHARED_VOIP_BLOCK
- SAME_DOMAIN
- SAME_ADDRESS
- SHARED_FLEX_HUB
- SHARED_PARCEL_CHAIN
- SIMILAR_NAME
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from . import config, db_v2


class EntityResolutionEngine:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(config.DATA_DIR / "sentinel_v2.db")
        self.virtual_keywords: List[str] = []
        self.virtual_addresses: List[str] = []
        self.parcel_chains: List[str] = []
        self._load_reference_data()

    def _load_reference_data(self) -> None:
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

    def resolve_relationships(self, businesses: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """Index all businesses and generate relational edges with confidence weights."""
        if businesses is None:
            businesses = db_v2.list_rows("businesses", db_path=self.db_path)

        total_b = len(businesses)
        print(f"[*] Resolving entities across {total_b} businesses...")

        # Fast Inverted Indexing
        phone_index: Dict[str, List[int]] = defaultdict(list)
        domain_index: Dict[str, List[int]] = defaultdict(list)
        address_index: Dict[str, List[int]] = defaultdict(list)
        prefix_index: Dict[str, List[int]] = defaultdict(list)
        brand_index: Dict[str, List[int]] = defaultdict(list)
        flex_hub_index: Dict[str, List[int]] = defaultdict(list)
        parcel_index: Dict[str, List[int]] = defaultdict(list)

        biz_lookup: Dict[int, Dict[str, Any]] = {}

        for b in businesses:
            b_id = b["id"]
            biz_lookup[b_id] = b

            phone = (b.get("normalized_phone") or "").strip()
            digits = re.sub(r"\D", "", phone)
            if len(digits) >= 8:
                phone_index[digits].append(b_id)

            prefix = (b.get("phone_prefix") or "").strip()
            if len(prefix) == 6:
                prefix_index[prefix].append(b_id)

            domain = (b.get("domain") or "").strip().lower()
            if domain and domain not in ("google.com", "facebook.com", "instagram.com", "maps.google.com"):
                domain_index[domain].append(b_id)

            postal = (b.get("postal_code") or "").strip().upper()
            house = (b.get("house_number") or "").strip()
            if postal and house:
                addr_key = f"{postal}_{house}"
                address_index[addr_key].append(b_id)

            brand = (b.get("normalized_name") or "").strip().lower()
            if len(brand) >= 4:
                brand_index[brand].append(b_id)

            raw_addr = (b.get("address") or "").lower()
            for kw in self.virtual_keywords:
                if kw in raw_addr:
                    flex_hub_index[kw].append(b_id)
                    break
            for known_addr in self.virtual_addresses:
                if known_addr in raw_addr:
                    flex_hub_index[known_addr].append(b_id)
                    break

            for chain in self.parcel_chains:
                if chain in raw_addr:
                    parcel_index[chain].append(b_id)
                    break

        relationships: List[Dict[str, Any]] = []
        seen_pairs: Set[Tuple[int, int, str]] = set()

        def add_rel(src: int, tgt: int, rel_type: str, weight: float, details: dict):
            if src == tgt:
                return
            pair_key = (min(src, tgt), max(src, tgt), rel_type)
            if pair_key in seen_pairs:
                return
            seen_pairs.add(pair_key)
            relationships.append({
                "source_business_id": min(src, tgt),
                "target_business_id": max(src, tgt),
                "relationship_type": rel_type,
                "weight": weight,
                "details_json": json.dumps(details, ensure_ascii=False)
            })

        # 1. Exact Phone Matches
        for ph, ids in phone_index.items():
            if len(ids) > 1:
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        add_rel(ids[i], ids[j], "SAME_PHONE", 1.0, {"phone": ph})

        # 2. Exact Domain Matches
        for dom, ids in domain_index.items():
            if len(ids) > 1:
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        add_rel(ids[i], ids[j], "SAME_DOMAIN", 1.0, {"domain": dom})

        # 3. Exact Address Matches (Postal + House Number)
        for addr, ids in address_index.items():
            if len(ids) > 1:
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        add_rel(ids[i], ids[j], "SAME_ADDRESS", 0.95, {"address_key": addr})

        # 4. Shared VoIP PBX Trunk Blocks (6-digit prefix e.g. 020369 across distinct cities)
        for pbx, ids in prefix_index.items():
            if len(ids) >= 2:
                # Check if multi-profile
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        add_rel(ids[i], ids[j], "SHARED_VOIP_BLOCK", 0.75, {"prefix": pbx})

        # 5. Shared Flex Hubs
        for hub, ids in flex_hub_index.items():
            if len(ids) > 1:
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        add_rel(ids[i], ids[j], "SHARED_FLEX_HUB", 0.85, {"hub": hub})

        # 6. Shared Parcel / Drop-off Chains
        for chain, ids in parcel_index.items():
            if len(ids) > 1:
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        add_rel(ids[i], ids[j], "SHARED_PARCEL_CHAIN", 0.85, {"chain": chain})

        # 7. Brand / Name Similarity
        for brand, ids in brand_index.items():
            if len(ids) > 1:
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        add_rel(ids[i], ids[j], "SIMILAR_NAME", 0.70, {"brand": brand})

        print(f"[+] Discovered {len(relationships)} distinct relational edges.")

        # Persist to database in batch
        with db_v2.transaction(self.db_path) as conn:
            conn.execute("DELETE FROM relationships")
            conn.executemany(
                """
                INSERT OR REPLACE INTO relationships (
                    source_business_id, target_business_id, relationship_type, weight, details_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        r["source_business_id"],
                        r["target_business_id"],
                        r["relationship_type"],
                        r["weight"],
                        r["details_json"]
                    )
                    for r in relationships
                ]
            )

        print(f"[+] Persisted {len(relationships)} relationships to {self.db_path}.")
        return relationships

    def get_relationships_for_business(self, business_id: int) -> List[Dict[str, Any]]:
        """Fetch all relationships connected to a specific business."""
        rows = db_v2.list_rows(
            "relationships",
            where="source_business_id = ? OR target_business_id = ?",
            params=(business_id, business_id),
            db_path=self.db_path
        )
        return rows
