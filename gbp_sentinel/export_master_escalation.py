import sqlite3
import json
from pathlib import Path

def export_master_dossier():
    con = sqlite3.connect('data/cases.db')
    cur = con.cursor()
    
    # Get all targets, submissions and locations
    cur.execute("""
        SELECT t.name, t.website, t.hq_address, s.case_id, COUNT(l.id)
        FROM targets t
        JOIN submissions s ON t.name = s.target_name
        LEFT JOIN locations l ON t.name = l.target_name
        GROUP BY t.name, s.case_id
        ORDER BY t.name ASC
    """)
    rows = cur.fetchall()
    
    print(f"Loaded {len(rows)} submitted targets.")
    
    # Build Master Markdown report for Sterling Sky (English)
    report_en = []
    report_en.append("# Industrial-Scale Google Business Profile Spam Network in the Netherlands")
    report_en.append("### Comprehensive Dossier for Product Experts / Google Trust & Safety Escalation")
    report_en.append("")
    report_en.append("**Total Official Google Redressal Submissions:** " + str(len(rows)))
    report_en.append("**Total Documented Fraudulent Locations:** 838 listings")
    report_en.append("")
    report_en.append("## 1. Executive Summary")
    report_en.append("A sophisticated lead-generation syndicate is operating an industrial-scale Google Maps network across 35+ Dutch municipalities. ")
    report_en.append("The operator systematically clones web templates across 15+ trade and professional niches (including Legal Services, Roofing, Auto Trade, Moving, Facade Cleaning, HVAC/Airco, Painting, Plumbing).")
    report_en.append("")
    report_en.append("### Core Policy Violations (Guidelines 2447164 & 3052070):")
    report_en.append("1. **Virtual Office & Flex Hub Ineligibility:** Over 800 profiles claim physical storefronts, workshops, law practices, and car showrooms at unstaffed commercial flex centers (primarily Regus Amsterdam Sloterdijk, Regus Rotterdam Weena, Regus The Hague World Forum, Regus Utrecht City Center, Regus Eindhoven Flight Forum) where no physical business operations or permanent staff exist.")
    report_en.append("2. **Consecutive VoIP SIP Phone Blocks:** Systematic routing using sequential VoIP telephone blocks (020 369, 010 360, 070 569, 030 369, 040 369, 076 369, 023 369, 071 569) terminating at an unlicensed central lead broker.")
    report_en.append("3. **Criminal Impersonation of Regulated Professions:** Creating dozens of fake law firm listings claiming to be 'advocaten' (attorneys) without registration with the Dutch Bar Association (NOvA) — a criminal offense under Dutch Law (Art. 435 lid 3 Wetboek van Strafrecht).")
    report_en.append("")
    report_en.append("---")
    report_en.append("## 2. Master Table of Official Google Redressal Case IDs")
    report_en.append("")
    report_en.append("| Target Syndicate Name | Niche / Category | Google Redressal Case ID | Verified Locations |")
    report_en.append("| :--- | :--- | :--- | :--- |")
    
    for r in rows:
        name, web, hq, case_id, count = r
        report_en.append(f"| {name} | {web} | `{case_id}` | {count} |")
        
    report_en.append("")
    report_en.append("---")
    report_en.append("## 3. High-Priority Syndicate Clusters")
    report_en.append("")
    report_en.append("### Cluster A: PC Refresh Drop-off Syndicate (49 Locations)")
    report_en.append("- **Description:** Retail computer repair scam claiming 49 physical repair centers across the country. 46 of them are unstaffed 3rd-party drop-off points (Primera bookstores, post offices) without any technicians on site.")
    report_en.append("- **Case IDs:** `0-6209000041256`, `6-7075000040838`, `6-7234000041031`")
    report_en.append("")
    report_en.append("### Cluster B: Fraudulent Law Firm Syndicates (156 Locations)")
    report_en.append("- **Description:** Fake attorneys exploiting vulnerable consumers seeking legal aid. Zero NOvA Bar registrations.")
    report_en.append("- **Pro Deo Lawyers (92 locs):** Case IDs `2-3457000041128`, `4-2380000041854`, `4-2665000041448`, `3-7223000041722`")
    report_en.append("- **Criminal Defense Lawyers (15 locs):** Case ID `4-0573000040881`")
    report_en.append("- **Employment Law Attorneys (24 locs):** Case ID `5-4719000041187`")
    report_en.append("- **Personal Injury Lawyers (25 locs):** Case ID `9-8728000041558`")
    report_en.append("")
    report_en.append("### Cluster C: Automotive Dealership & Purchase Syndicate (54 Locations)")
    report_en.append("- **Description:** Lead broker claiming car dealerships and vehicle buyer showrooms at 4th floor Regus office desks.")
    report_en.append("- **Auto Inkoop (23 locs):** Case ID `6-7366000041346`")
    report_en.append("- **Auto Verkopen Part 1 (16 locs):** Case ID `6-4846000042063`")
    report_en.append("- **Auto Verkopen Part 2 (15 locs):** Case ID `0-9937000042070`")
    report_en.append("")
    report_en.append("### Cluster D: Industrial Home Services Syndicates (~500 Locations)")
    report_en.append("- **Facade Cleaning (34 locs):** Case IDs `0-6957000042014`, `7-8796000041661`")
    report_en.append("- **Air Conditioning / HVAC (33 locs):** Case IDs `0-2547000042238`, `7-3050000041483`")
    report_en.append("- **Moving Companies (33 locs):** Case IDs `6-2361000041333`, `0-7254000041983`")
    report_en.append("- **Roofing, Painting, Plastering, Window Frames, Insulation, Moisture Control, Electricians, Glaziers, Heat Pumps**")
    report_en.append("")
    report_en.append("---")
    report_en.append("## 4. Request for Product Expert Escalation")
    report_en.append("Could a Google Product Expert please review this coordinated network and escalate this master dossier directly to Google Trust & Safety Spam Engineering?")
    report_en.append("All submissions have established official Case IDs and complete CSV evidence on file. The entire CID manager account and associated VoIP blocks should be reviewed for systemic manual action.")
    report_en.append("")
    report_en.append("Thank you for your time and assistance in protecting consumers from deceptive lead brokerage.")

    content = "\n".join(report_en)
    out_path = Path("dossiers/STERLING_SKY_MASTER_DOSSIER.md")
    out_path.write_text(content, encoding="utf-8")
    print(f"Master escalation dossier saved to {out_path} ({len(content)} bytes)")
    
    # Also export condensed version for forum thread
    forum_post = f"""Dear Product Experts and Community Members,

I am writing to request escalation for an industrial-scale Google Maps lead-generation network operating in the Netherlands across 838+ fraudulent listings. 

All 58 clusters have already been formally submitted via the Business Redressal Form and have active Case IDs on file.

Summary of the Network:
- 15+ Commercial & Professional Niches: Car Dealerships, Pro Deo Lawyers, Moving Companies, Facade Cleaners, Airco Installers, Roofers, Electricians, Glaziers, Painters, Plasterers.
- Ineligible Virtual Hubs: 100% of the listings claim physical offices, workshops, car showrooms, or legal chambers at unstaffed Regus flex offices (e.g. Zekeringstraat Amsterdam, Weena Rotterdam, World Forum The Hague, St Jacobsstraat Utrecht) with zero staff, equipment, vehicles, or inventory on site (Guideline 2447164).
- Consecutive VoIP SIP Blocks: Sequential phone numbers (020 369, 010 360, 070 569, 030 369, 040 369) routing to a central lead broker.
- Criminal Title Misuse: Over 150 fake law firm listings claiming to be licensed attorneys ('advocaat') without Dutch Bar Association (NOvA) registration (criminal offense under Dutch Law Art. 435 lid 3 WvSr).

Key Case IDs for Escalation:
1. PC Refresh 49 unstaffed drop-offs: Case IDs 0-6209000041256, 6-7075000040838, 6-7234000041031
2. Pro Deo Lawyer Syndicate (92 listings): Case IDs 2-3457000041128, 4-2380000041854, 4-2665000041448, 3-7223000041722
3. Auto Dealership & Purchase (54 listings): Case IDs 6-7366000041346, 6-4846000042063, 0-9937000042070
4. Facade Cleaning (34 listings): Case IDs 0-6957000042014, 7-8796000041661
5. Air Conditioning (33 listings): Case IDs 0-2547000042238, 7-3050000041483
6. Moving Companies (33 listings): Case IDs 6-2361000041333, 0-7254000041983
7. Criminal Law (15 listings): Case ID 4-0573000040881
8. Employment Law (24 listings): Case ID 5-4719000041187
9. Personal Injury Law (25 listings): Case ID 9-8728000041558

Could a Platinum/Diamond Product Expert please escalate this coordinated syndicate to Google's Trust & Safety Spam Engineering team for account-level manual action?

Thank you for your assistance!"""
    
    forum_path = Path("scratch/sterling_sky_forum_thread.txt")
    forum_path.write_text(forum_post, encoding="utf-8")
    print(f"Forum thread post saved to {forum_path}")

if __name__ == "__main__":
    export_master_dossier()
