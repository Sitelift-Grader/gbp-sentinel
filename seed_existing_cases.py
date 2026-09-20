"""Import existing investigated cases (PC Refresh & Dak Advies Groep) into SQLite DB."""

import csv
from pathlib import Path
from gbp_sentinel import db, config

def import_cases():
    db.init_db()

    # 1. Import PC Refresh
    pc_csv = Path(r"C:\Users\danny\.gemini\antigravity\scratch\pc_refresh_gbp_redressal_dossier.csv")
    if pc_csv.exists():
        print("Importing PC Refresh data...")
        db.save_target(
            name="PC Refresh",
            kvk="54482844",
            website="https://www.pcrefresh.com",
            hq_address="Stephensonstraat 48, 2561 XW Den Haag"
        )
        locations = []
        with open(pc_csv, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                locations.append({
                    "name": row.get("business_name_on_profile", ""),
                    "url": row.get("google_maps_url", ""),
                    "address": row.get("physical_address", ""),
                    "actual_occupant": row.get("actual_occupant_and_business_type", ""),
                    "kvk_status": row.get("commercial_register_kvk_status", ""),
                    "policy_violation_details": row.get("policy_violation_details", ""),
                    "is_fraud": "None" not in row.get("policy_violation_details", "")
                })
        db.save_locations("PC Refresh", locations)
        db.save_submission(
            target_name="PC Refresh",
            case_id="4-8919000041358",
            email="ddpzonly@gmail.com",
            dossier_path=str(pc_csv),
            filled_screenshot=r"C:\Users\danny\.gemini\antigravity\scratch\redressal_form_filled.png",
            result_screenshot=r"C:\Users\danny\.gemini\antigravity\scratch\redressal_submission_result.png",
            status="submitted"
        )
        print(f"Imported PC Refresh with {len(locations)} locations and Case ID 4-8919000041358")

    # 2. Import Dak Advies Groep
    dak_csv = Path(r"C:\Users\danny\.gemini\antigravity\scratch\dak_advies_groep_gbp_redressal_dossier.csv")
    if dak_csv.exists():
        print("Importing Dak Advies Groep data...")
        db.save_target(
            name="Dak Advies Groep B.V.",
            kvk="93618166",
            website="https://www.dakadviesgroep.nl",
            hq_address="Naarderweg 16, 1217 GL Hilversum"
        )
        locations = []
        with open(dak_csv, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                locations.append({
                    "name": row.get("business_name_on_profile", ""),
                    "url": row.get("google_maps_url", ""),
                    "address": row.get("physical_address", ""),
                    "actual_occupant": row.get("actual_occupant_and_business_type", ""),
                    "kvk_status": row.get("commercial_register_kvk_status", ""),
                    "policy_violation_details": row.get("policy_violation_details", ""),
                    "is_fraud": True
                })
        db.save_locations("Dak Advies Groep B.V.", locations)
        db.save_submission(
            target_name="Dak Advies Groep B.V.",
            case_id="2-9725000041046",
            email="ddpzonly@gmail.com",
            dossier_path=str(dak_csv),
            filled_screenshot=r"C:\Users\danny\.gemini\antigravity\scratch\redressal_form_filled_dakadvies.png",
            result_screenshot=r"C:\Users\danny\.gemini\antigravity\scratch\redressal_submission_result_dakadvies.png",
            status="submitted"
        )
        print(f"Imported Dak Advies Groep B.V. with {len(locations)} locations and Case ID 2-9725000041046")

if __name__ == "__main__":
    import_cases()
