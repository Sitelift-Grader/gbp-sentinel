"""Network analysis, graph clustering, and scoring engine for GBP SMOKER / Sentinel.

Uses NetworkX to detect multi-profile clusters, calculate transparent
Network Suspicion Scores (0-100), and generate Cytoscape graph payloads.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import networkx as nx

from . import config, db_v2


class NetworkEngine:
    DISCLAIMER = (
        "Dit is een technische prioriteringsscore voor nader onderzoek "
        "en geen vaststelling van een policy violation."
    )

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(config.DATA_DIR / "sentinel_v2.db")

    def build_and_cluster(self, min_cluster_size: int = 2) -> List[Dict[str, Any]]:
        """Construct graph from relational edges, isolate clusters, compute scores, and save to DB."""
        print("[*] Loading businesses and relationships for network graph...")
        businesses = db_v2.list_rows("businesses", db_path=self.db_path)
        biz_by_id = {b["id"]: b for b in businesses}

        relationships = db_v2.list_rows("relationships", db_path=self.db_path)
        print(f"[+] Loaded {len(businesses)} businesses and {len(relationships)} relationships.")

        G = nx.Graph()
        for b_id, b in biz_by_id.items():
            G.add_node(
                b_id,
                name=b.get("name", ""),
                domain=b.get("domain", ""),
                phone=b.get("normalized_phone", ""),
                address=b.get("address", ""),
                city=b.get("city", ""),
            )

        for r in relationships:
            src = r["source_business_id"]
            tgt = r["target_business_id"]
            if src in biz_by_id and tgt in biz_by_id:
                G.add_edge(
                    src,
                    tgt,
                    rel_type=r["relationship_type"],
                    weight=r["weight"],
                )

        # Community clustering via connected components
        components = list(nx.connected_components(G))
        clusters = []
        cluster_idx = 1

        print(f"[*] Found {len(components)} connected components in total.")

        with db_v2.transaction(self.db_path) as conn:
            conn.execute("DELETE FROM network_members")
            conn.execute("DELETE FROM networks")

            for comp in components:
                member_ids = list(comp)
                if len(member_ids) < min_cluster_size:
                    continue

                subgraph = G.subgraph(member_ids)
                member_bizs = [biz_by_id[m_id] for m_id in member_ids]

                # Aggregate attributes
                unique_domains = {b.get("domain") for b in member_bizs if b.get("domain")}
                unique_phones = {b.get("normalized_phone") for b in member_bizs if b.get("normalized_phone")}
                unique_addresses = {b.get("postal_code") for b in member_bizs if b.get("postal_code")}
                unique_names = {b.get("normalized_name") for b in member_bizs if b.get("normalized_name")}

                # Determine dominant name / theme
                first_name = member_bizs[0].get("normalized_name") or member_bizs[0].get("name", "Unknown Cluster")
                network_code = f"NETWORK-{cluster_idx:05d}"

                # Calculate explainable score
                score_data = self.calculate_suspicion_score(
                    member_count=len(member_bizs),
                    domain_count=len(unique_domains),
                    phone_count=len(unique_phones),
                    address_count=len(unique_addresses),
                    subgraph=subgraph,
                    member_bizs=member_bizs,
                )

                network_record = {
                    "network_code": network_code,
                    "name": f"{first_name.title()} Syndicate ({len(member_bizs)} profiles)",
                    "network_type": score_data["network_type"],
                    "suspicion_score": score_data["total_score"],
                    "score_breakdown_json": json.dumps(score_data, ensure_ascii=False),
                    "member_count": len(member_bizs),
                    "address_count": len(unique_addresses),
                    "domain_count": len(unique_domains),
                    "phone_count": len(unique_phones),
                    "status": "DISCOVERED",
                }

                cur = conn.execute(
                    """
                    INSERT INTO networks (
                        network_code, name, network_type, suspicion_score, score_breakdown_json,
                        member_count, address_count, domain_count, phone_count, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        network_record["network_code"],
                        network_record["name"],
                        network_record["network_type"],
                        network_record["suspicion_score"],
                        network_record["score_breakdown_json"],
                        network_record["member_count"],
                        network_record["address_count"],
                        network_record["domain_count"],
                        network_record["phone_count"],
                        network_record["status"],
                    ),
                )
                net_id = cur.lastrowid

                # Update suspicion_score on businesses
                for m_id in member_ids:
                    conn.execute(
                        """
                        INSERT INTO network_members (network_id, business_id, membership_strength)
                        VALUES (?, ?, ?)
                        """,
                        (net_id, m_id, 1.0),
                    )
                    conn.execute(
                        "UPDATE businesses SET suspicion_score = ? WHERE id = ?",
                        (score_data["total_score"], m_id),
                    )

                network_record["id"] = net_id
                network_record["member_ids"] = member_ids
                clusters.append(network_record)
                cluster_idx += 1

        print(f"[+] Reconstructed {len(clusters)} multi-profile networks (>= {min_cluster_size} profiles).")
        return clusters

    def calculate_suspicion_score(
        self,
        member_count: int,
        domain_count: int,
        phone_count: int,
        address_count: int,
        subgraph: nx.Graph,
        member_bizs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compute transparent, explainable Network Suspicion Score (0-100)."""
        score = 0
        reasons: List[Dict[str, Any]] = []

        # 1. Profile concentration
        if member_count >= 10:
            score += 25
            reasons.append({"points": 25, "reason": f"Omvangrijk netwerk met {member_count} gekoppelde bedrijfsprofielen."})
        elif member_count >= 5:
            score += 15
            reasons.append({"points": 15, "reason": f"Netwerk met {member_count} onderling verbonden profielen."})
        elif member_count >= 2:
            score += 8
            reasons.append({"points": 8, "reason": f"Meerdere profielen ({member_count}) delen infrastructuur."})

        # 2. Shared Domain footprint
        if domain_count == 1 and member_count >= 3:
            score += 25
            reasons.append({"points": 25, "reason": "Identieke website/domeinnaam gebruikt door meerdere verschillende locaties."})
        elif domain_count > 1 and domain_count <= 3 and member_count >= 5:
            score += 15
            reasons.append({"points": 15, "reason": f"Sterk geconcentreerde domeininfrastructuur ({domain_count} domeinen over {member_count} profielen)."})

        # 3. Shared Phone / PBX
        if phone_count == 1 and member_count >= 2:
            score += 20
            reasons.append({"points": 20, "reason": "Eén enkel telefoonnummer gedeeld door meerdere afzonderlijke Maps-profielen."})
        elif phone_count > 1 and phone_count <= (member_count / 2):
            score += 12
            reasons.append({"points": 12, "reason": "Herhaaldelijk gedeelde telefonie en centrale doorschakeling."})

        # 4. Check for VoIP prefixes (085 / 088 / 020-369)
        has_voip = any((b.get("phone_prefix") or "").startswith(("085", "088")) for b in member_bizs)
        has_pbx_369 = any("369" in (b.get("phone_prefix") or "") for b in member_bizs)
        if has_pbx_369:
            score += 15
            reasons.append({"points": 15, "reason": "Gedetecteerd 0XX-369 SIP trunk VoIP-blok (karakteristiek voor multi-regio dispatch)."})
        elif has_voip:
            score += 10
            reasons.append({"points": 10, "reason": "Gebruik van landelijke 085/088 VoIP-nummers voor lokale vermeldingen."})

        # 5. Shared Address multi-tenancy
        if address_count == 1 and member_count >= 3:
            score += 20
            reasons.append({"points": 20, "reason": f"Precies hetzelfde vestigingsadres geclaimd door {member_count} profielen."})

        total_score = min(100, max(0, score))

        if total_score >= 70:
            severity = "CRITICAL"
        elif total_score >= 50:
            severity = "HIGH"
        elif total_score >= 30:
            severity = "MEDIUM"
        else:
            severity = "LOW"

        # Categorize network type
        if domain_count == 1 and member_count >= 4:
            network_type = "LEAD_GEN_CLONE"
        elif has_pbx_369 or (has_voip and member_count >= 5):
            network_type = "CROSS_NICHE_PBX"
        elif address_count == 1 and member_count >= 3:
            network_type = "VIRTUAL_OFFICE_HUB"
        else:
            network_type = "COORDINATED_CLUSTER"

        return {
            "total_score": total_score,
            "severity": severity,
            "network_type": network_type,
            "reasons": reasons,
            "disclaimer": self.DISCLAIMER,
        }

    def to_cytoscape_elements(self, network_id: int) -> Dict[str, List[Dict[str, Any]]]:
        """Convert a network cluster into Cytoscape.js nodes and edges."""
        members = db_v2.list_rows("network_members", where="network_id = ?", params=(network_id,), db_path=self.db_path)
        member_biz_ids = [m["business_id"] for m in members]

        if not member_biz_ids:
            return {"nodes": [], "edges": []}

        placeholders = ", ".join("?" for _ in member_biz_ids)
        biz_rows = db_v2.list_rows(
            "businesses",
            where=f"id IN ({placeholders})",
            params=tuple(member_biz_ids),
            db_path=self.db_path,
        )

        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []

        seen_entities: Set[str] = set()

        for b in biz_rows:
            b_id_str = f"biz_{b['id']}"
            nodes.append({
                "data": {
                    "id": b_id_str,
                    "label": b.get("name", "Business"),
                    "type": "business",
                    "city": b.get("city", ""),
                    "score": b.get("suspicion_score", 0),
                    "url": b.get("google_maps_url", ""),
                }
            })

            # Domain node
            domain = b.get("domain")
            if domain:
                dom_id = f"dom_{domain}"
                if dom_id not in seen_entities:
                    seen_entities.add(dom_id)
                    nodes.append({"data": {"id": dom_id, "label": domain, "type": "domain"}})
                edges.append({"data": {"source": b_id_str, "target": dom_id, "label": "USES_DOMAIN"}})

            # Phone node
            phone = b.get("normalized_phone")
            if phone:
                phone_id = f"phone_{phone}"
                if phone_id not in seen_entities:
                    seen_entities.add(phone_id)
                    nodes.append({"data": {"id": phone_id, "label": phone, "type": "phone"}})
                edges.append({"data": {"source": b_id_str, "target": phone_id, "label": "USES_PHONE"}})

            # Postal node
            postal = b.get("postal_code")
            if postal:
                post_id = f"addr_{postal}"
                if post_id not in seen_entities:
                    seen_entities.add(post_id)
                    nodes.append({"data": {"id": post_id, "label": f"{postal} {b.get('city', '')}", "type": "address"}})
                edges.append({"data": {"source": b_id_str, "target": post_id, "label": "LOCATED_AT"}})

        return {"nodes": nodes, "edges": edges}
