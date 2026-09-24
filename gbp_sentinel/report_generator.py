"""Forensic Report Generator for GBP SMOKER / Sentinel.

Generates objective, evidence-backed dossiers for investigated networks and cases.
Complies with Section 18 of the GBP SMOKER specification:
- Executive summary (strictly objective, no unverified fraud claims)
- Network overview (member counts, relationship metrics)
- Individual profiles (name, Maps URL, location, website, phone, observations, evidence, policy)
- Network relationships (structured graph and relationship table)
- Policy mapping (Policy, Observation, Evidence, Confidence)
- Recommended action: "Consider submitting this evidence through Google's official reporting process for review."
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from . import config, db_v2


class ReportGenerator:
    """Generates objective forensic investigation dossiers in GitHub-flavored Markdown."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = str(db_path or (config.DATA_DIR / "sentinel_v2.db"))

    def generate_network_report(self, network_id: int) -> str:
        net = db_v2.get("networks", network_id, db_path=self.db_path)
        if not net:
            return f"# Dossier niet gevonden\n\nNetwerk met ID `{network_id}` is niet geregistreerd in de database."

        members = db_v2.list_rows("network_members", where="network_id = ?", params=(network_id,), db_path=self.db_path)
        biz_ids = [m["business_id"] for m in members]

        businesses = []
        if biz_ids:
            placeholders = ", ".join("?" for _ in biz_ids)
            businesses = db_v2.list_rows("businesses", where=f"id IN ({placeholders})", params=tuple(biz_ids), db_path=self.db_path)

        # Gather relationships
        rel_sql = "source_business_id IN ({0}) AND target_business_id IN ({0})".format(", ".join("?" for _ in biz_ids)) if biz_ids else "1=0"
        relationships = db_v2.list_rows("relationships", where=rel_sql, params=tuple(biz_ids + biz_ids), db_path=self.db_path) if biz_ids else []

        # Gather evidence & findings
        evidence_list = []
        findings_list = []
        if biz_ids:
            placeholders = ", ".join("?" for _ in biz_ids)
            evidence_list = db_v2.list_rows("evidence", where=f"business_id IN ({placeholders})", params=tuple(biz_ids), db_path=self.db_path)
            findings_list = db_v2.list_rows("policy_findings", where=f"business_id IN ({placeholders})", params=tuple(biz_ids), db_path=self.db_path)

        # Score breakdown
        score_breakdown = {}
        if net.get("score_breakdown_json"):
            try:
                score_breakdown = json.loads(net["score_breakdown_json"])
            except Exception:
                pass

        net_code = net.get("network_code") or net.get("cluster_identifier") or f"NETWORK-{network_id:05d}"
        net_type = net.get("network_type") or net.get("cluster_type") or "GENERAL_SYNDICATE"

        lines: List[str] = []
        lines.append(f"# Forensisch onderzoeksdossier: {net['name']}")
        lines.append(f"**Netwerk ID:** `{net_code}` | **Cluster type:** `{net_type}`")
        lines.append(f"**Prioriteringsscore:** `{net['suspicion_score']}/100`")
        lines.append("> *Toelichting: Dit is een technische prioriteringsscore voor nader onderzoek en geen vaststelling van een policy violation.*")
        lines.append("")

        # 1. Executive summary
        lines.append("## Executive summary")
        lines.append(
            f"Dit dossier documenteert een forensische analyse van een samenhangend cluster van {len(businesses)} Google Business Profile vermeldingen. "
            f"Het onderzoek heeft {len(relationships)} onderlinge infrastructurele relaties en {len(evidence_list)} concrete bewijsstukken vastgelegd. "
            "De analyse toetst de verzamelde feiten uitsluitend aan de officiële Google Business Profile richtlijnen zonder aannames vooraf."
        )
        lines.append("")

        # 2. Network overview
        lines.append("## Network overview")
        lines.append(f"- **Totaal aantal profielen:** {len(businesses)}")
        lines.append(f"- **Vastgelegde relaties:** {len(relationships)}")
        lines.append(f"- **Geregistreerde bewijspunten:** {len(evidence_list)}")
        lines.append(f"- **Mogelijke beleidssignalen:** {len(findings_list)}")
        if score_breakdown:
            lines.append("- **Onderbouwing prioriteringsscore:**")
            for reason in score_breakdown.get("reasons", []):
                lines.append(f"  - {reason}")
        lines.append("")

        # 3. Individual profiles
        lines.append("## Individual profiles")
        for b in businesses:
            lines.append(f"### {b['name']}")
            lines.append(f"- **Bedrijfs ID:** `{b['id']}`")
            lines.append(f"- **Adres:** {b['address'] or 'Niet vermeld / Service-area'}")
            lines.append(f"- **Plaats:** {b['city'] or 'Onbekend'}")
            lines.append(f"- **Telefoon:** {b['phone'] or 'Onbekend'} (genormaliseerd: `{b['normalized_phone'] or 'Geen'}`)")
            website_url = b.get("canonical_url") or b.get("website") or b.get("domain") or "Geen"
            source_st = b.get("source_status") or b.get("status") or "Onbekend"
            lines.append(f"- **Website:** {website_url}")
            lines.append(f"- **Status in register:** `{source_st}`")

            # Matched findings for this business
            b_findings = [f for f in findings_list if f["business_id"] == b["id"]]
            if b_findings:
                lines.append("- **Relevante beleidspunten:**")
                for bf in b_findings:
                    lines.append(f"  - **{bf['policy_id']}**: {bf.get('observation_text', 'Mogelijk beleidssignaal')} (Status: `{bf.get('status', 'POTENTIAL')}`)")
            lines.append("")

        # 4. Network relationships
        lines.append("## Network relationships")
        if relationships:
            lines.append("| Bron ID | Doel ID | Relatie type | Gewicht | Toelichting |")
            lines.append("| :--- | :--- | :--- | :--- | :--- |")
            for r in relationships[:50]:  # Cap at 50 for readability
                weight_val = r.get("weight", 1.0)
                details = r.get("details_json") or "Gedeelde infrastructuur"
                lines.append(f"| {r['source_business_id']} | {r['target_business_id']} | `{r['relationship_type']}` | {weight_val} | {details} |")
            if len(relationships) > 50:
                lines.append(f"\n*Tabel afgekapt op 50 van {len(relationships)} relaties. Zie de interactieve graaf voor het volledige overzicht.*")
        else:
            lines.append("Geen directe interne relaties geregistreerd.")
        lines.append("")

        # 5. Policy mapping
        lines.append("## Policy mapping")
        if findings_list:
            lines.append("| Policy ID | Bedrijf ID | Observatie / Signaal | Betrouwbaarheid | Status |")
            lines.append("| :--- | :--- | :--- | :--- | :--- |")
            for f in findings_list[:50]:
                obs = f.get("observation_text") or f.get("reasoning_summary") or "Beleidssignaal"
                lines.append(f"| `{f['policy_id']}` | {f['business_id']} | {obs} | {f.get('confidence', 'HIGH')} | `{f.get('status', 'POTENTIAL')}` |")
        else:
            lines.append("Geen actieve beleidssignalen geconstateerd binnen dit cluster.")
        lines.append("")

        # 6. Recommended action
        lines.append("## Recommended action")
        lines.append("Consider submitting this evidence through Google's official reporting process for review.")
        lines.append("")

        return "\n".join(lines)

    def generate_case_report(self, case_id: int) -> str:
        case = db_v2.get("cases", case_id, db_path=self.db_path)
        if not case:
            return f"# Dossier niet gevonden\n\nCase met ID `{case_id}` is niet geregistreerd."

        case_biz = db_v2.list_rows("case_businesses", where="case_id = ?", params=(case_id,), db_path=self.db_path)
        biz_ids = [cb["business_id"] for cb in case_biz]

        submissions = db_v2.list_rows("submissions", where="case_id = ?", params=(case_id,), db_path=self.db_path)
        outcomes = db_v2.list_rows("outcomes", where="case_id = ?", params=(case_id,), db_path=self.db_path)

        lines: List[str] = []
        lines.append(f"# Dossier: {case['case_identifier']}")
        lines.append(f"**Titel:** {case['title']}")
        lines.append(f"**Status:** `{case['status']}` | **Prioriteit:** `{case['priority']}`")
        lines.append(f"**Beoordelaar:** {case['reviewer_name'] or 'Nog niet toegewezen'}")
        lines.append("")

        lines.append("## Executive summary")
        lines.append(
            f"Dit onderzoeksdossier bevat {len(biz_ids)} bedrijfsprofiel(en). "
            f"Huidige status: {case['status']}. "
            f"Aantal geregistreerde indieningen bij Google: {len(submissions)}."
        )
        lines.append("")

        if submissions:
            lines.append("## Geregistreerde Google meldingen")
            lines.append("| Datum | Kanaal | Status | Google Case ID |")
            lines.append("| :--- | :--- | :--- | :--- |")
            for sub in submissions:
                lines.append(f"| {sub['submission_date']} | `{sub['reporting_channel']}` | `{sub['status']}` | `{sub['google_case_id'] or 'In afwachting'}` |")
            lines.append("")

        if outcomes:
            lines.append("## Waargenomen resultaten")
            for out in outcomes:
                lines.append(f"- **{out['outcome_type']}** ({out['observation_date']}): {out['details']}")
            lines.append("")

        lines.append("## Recommended action")
        lines.append("Consider submitting this evidence through Google's official reporting process for review.")
        lines.append("")

        return "\n".join(lines)
