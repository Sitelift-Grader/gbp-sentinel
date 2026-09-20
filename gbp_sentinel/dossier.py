"""Dossier generator for Google Redressal complaints."""

import csv
from pathlib import Path
from . import config

REDRESSAL_COLUMNS = [
    "business_name_on_profile",
    "google_maps_url",
    "physical_address",
    "actual_occupant_and_business_type",
    "commercial_register_kvk_status",
    "policy_violation_details"
]

def export_dossier_csv(target_name: str, audited_locations: list, filename: str = None) -> Path:
    """Export audited locations to a Google-compliant CSV file."""
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in target_name).lower()
    if not filename:
        filename = f"{safe_name}_gbp_redressal_dossier.csv"
    
    filepath = config.DOSSIERS_DIR / filename
    
    rows = []
    for loc in audited_locations:
        rows.append({
            "business_name_on_profile": loc.get("name", target_name),
            "google_maps_url": loc.get("url", f"https://www.google.com/maps/search/?api=1&query={loc.get('address', '')}"),
            "physical_address": loc.get("address", "Address unverified"),
            "actual_occupant_and_business_type": loc.get("actual_occupant", "Unstaffed Shared Facility"),
            "commercial_register_kvk_status": loc.get("kvk_status", "Unregistered at this location"),
            "policy_violation_details": loc.get("policy_violation_details", loc.get("violation_details", "Policy violation"))
        })

    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REDRESSAL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return filepath

def generate_explanation_text(
    target_name: str,
    target_kvk: str,
    target_hq: str,
    total_locations: int,
    primary_violations: list = None
) -> str:
    """Generate concise, policy-focused English explanation text under 1000 characters."""
    if not primary_violations:
        primary_violations = [
            "Virtual Offices / Coworking: Listings at shared desk spaces without permanent on-site staff during stated hours.",
            "Service Area Business: Does not conduct face-to-face business at these locations; addresses must be hidden.",
            "Deceptive Titles: Manipulated profile names with artificial local keyword stuffing."
        ]

    intro = (
        f"{target_name} (KvK {target_kvk or 'Commercial Register'}) operates a nationwide "
        f"network of ineligible Google Business Profiles across the Netherlands.\n\n"
        f"1. VIOLATION SUMMARY:\n"
        f"The business maintains statutory presence at {target_hq or 'HQ'}, but has established "
        f"{total_locations} fake satellite storefronts. These locations are unstaffed virtual "
        f"offices (Regus, Spaces), third-party retail drop-offs, or private residential addresses.\n\n"
        f"2. GOOGLE POLICY BREACHES:\n"
    )

    bullets = "".join(f"- {v}\n" for v in primary_violations)
    outro = f"\nAttached CSV contains all {total_locations} audited fake locations."

    full_text = intro + bullets + outro

    # Hard cap check
    if len(full_text) > 1000:
        # Trim gracefully
        allowed_len = 1000 - len(intro) - len(outro) - 10
        bullets = bullets[:allowed_len].rsplit("\n", 1)[0] + "\n"
        full_text = intro + bullets + outro

    return full_text
