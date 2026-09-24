"""Migrate historical data (1,496 locations) from data/cases.db into data/sentinel_v2.db.

All imported records are marked source_status = 'unverified_historical'.
Legacy subjective 'is_fraud' tags are archived into historical snapshots
without prejudicing objective re-evaluation.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gbp_sentinel import config, db_v2, normalizer



def migrate():
    v1_path = config.DB_PATH
    v2_path = config.DATA_DIR / "sentinel_v2.db"
    backup_path = config.DATA_DIR / "cases.db.v1.bak"

    print(f"[*] Starting migration from {v1_path} to {v2_path}...")

    # Step 1: Backup
    if v1_path.exists() and not backup_path.exists():
        shutil.copy2(v1_path, backup_path)
        print(f"[+] Created safety backup at {backup_path}")

    # Step 2: Initialize v2 database
    db_v2.init_db(str(v2_path))
    print(f"[+] Initialized relational schema in {v2_path}")

    # Step 3: Read v1 database
    v1_conn = sqlite3.connect(v1_path)
    v1_conn.row_factory = sqlite3.Row
    v1_cur = v1_conn.cursor()

    locations = v1_cur.execute("SELECT id, target_name, data, created_at, liveness_status FROM locations").fetchall()
    print(f"[+] Found {len(locations)} raw locations in legacy database.")

    targets = {r["name"]: dict(r) for r in v1_cur.execute("SELECT * FROM targets").fetchall()}
    submissions = v1_cur.execute("SELECT * FROM submissions").fetchall()
    print(f"[+] Found {len(targets)} targets and {len(submissions)} submission records.")

    v1_conn.close()

    # Step 4: Ingest into v2
    v2_conn = db_v2.get_connection(str(v2_path))
    migrated_count = 0
    skipped_count = 0

    now_iso = datetime.now(timezone.utc).isoformat()

    with v2_conn:
        for loc in locations:
            raw_data_str = loc["data"]
            try:
                data = json.loads(raw_data_str)
            except Exception:
                skipped_count += 1
                continue

            raw_name = data.get("name", "") or loc["target_name"] or "Unknown Business"
            raw_address = data.get("address", "") or ""
            raw_phone = data.get("phone", "") or ""
            raw_website = data.get("website", "") or ""
            url = data.get("url", "") or ""
            place_id = data.get("place_id", "") or ""

            if not place_id:
                # Derive deterministic place_id from url or address + name hash
                if url and "1s0x" in url:
                    m = re.search(r"1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)", url)
                    place_id = m.group(1) if m else url
                else:
                    place_id = "v1_" + hashlib.md5(f"{raw_name}_{raw_address}".encode()).hexdigest()[:16]

            # Normalization
            norm_phone = normalizer.normalize_phone(raw_phone)
            norm_addr = normalizer.normalize_address(raw_address)
            norm_dom = normalizer.normalize_domain(raw_website)
            norm_name = normalizer.normalize_business_name(raw_name)

            # Check if exists
            existing = v2_conn.execute("SELECT id FROM businesses WHERE place_id = ?", (place_id,)).fetchone()
            if existing:
                business_id = existing["id"]
            else:
                cur = v2_conn.execute(
                    """
                    INSERT INTO businesses (
                        place_id, google_maps_url, name, raw_name, normalized_name,
                        phone, normalized_phone, phone_prefix, domain, canonical_url,
                        address, street, house_number, postal_code, city, country,
                        category, rating, review_count, source_status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        place_id,
                        url,
                        norm_name["clean_name"],
                        raw_name,
                        norm_name["brand_guess"],
                        raw_phone,
                        norm_phone["national"],
                        norm_phone["pbx_prefix_6"],
                        norm_dom["domain"],
                        norm_dom["canonical_url"],
                        raw_address,
                        norm_addr["street"],
                        norm_addr["house_number"],
                        norm_addr["postal_code"],
                        norm_addr["city"],
                        norm_addr["country"],
                        data.get("category", "Contractor"),
                        float(data.get("rating", 0.0) or 0.0),
                        int(data.get("review_count", 0) or 0),
                        "unverified_historical",
                        loc["created_at"] or now_iso,
                        now_iso,
                    ),
                )
                business_id = cur.lastrowid

            # Save initial snapshot
            snap_hash = hashlib.sha256(raw_data_str.encode()).hexdigest()
            try:
                v2_conn.execute(
                    """
                    INSERT OR IGNORE INTO business_snapshots (
                        business_id, snapshot_timestamp, name, address, phone,
                        website, category, status_visible, raw_payload_json, sha256_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        business_id,
                        loc["created_at"] or now_iso,
                        raw_name,
                        raw_address,
                        raw_phone,
                        raw_website,
                        data.get("category", ""),
                        loc["liveness_status"] or "unknown",
                        raw_data_str,
                        snap_hash,
                    ),
                )
            except Exception:
                pass

            migrated_count += 1

        # Migrate Submissions to Cases & Submissions
        for sub in submissions:
            target_name = sub["target_name"]
            case_id_code = sub["case_id"] or f"LEGACY-{sub['id']}"
            status = "REPORTED" if sub["case_id"] else "PREPARED"

            case_cur = v2_conn.execute(
                """
                INSERT OR IGNORE INTO cases (
                    case_code, title, priority, status, reviewer_name, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"CASE-{case_id_code}",
                    f"Investigation Dossier: {target_name}",
                    "HIGH",
                    status,
                    sub["email"] or "Compliance Officer",
                    f"Migrated legacy submission for {target_name}",
                    sub["created_at"] or now_iso,
                    now_iso,
                ),
            )

            # Retrieve case id
            case_row = v2_conn.execute("SELECT id FROM cases WHERE case_code = ?", (f"CASE-{case_id_code}",)).fetchone()
            if case_row:
                v2_conn.execute(
                    """
                    INSERT INTO submissions (
                        case_id, submission_type, google_case_id,
                        submission_payload_csv, filled_screenshot_path,
                        result_screenshot_path, status, submitted_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        case_row["id"],
                        "GOOGLE_REDRESSAL_FORM",
                        sub["case_id"],
                        sub["dossier_path"],
                        sub["filled_screenshot"],
                        sub["result_screenshot"],
                        sub["status"] or "submitted",
                        sub["created_at"],
                        now_iso,
                    ),
                )

    v2_conn.close()

    # Verification queries
    verify_conn = db_v2.get_connection(str(v2_path))
    total_b = verify_conn.execute("SELECT COUNT(*) FROM businesses").fetchone()[0]
    total_s = verify_conn.execute("SELECT COUNT(*) FROM business_snapshots").fetchone()[0]
    total_c = verify_conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    total_sub = verify_conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
    distinct_domains = verify_conn.execute("SELECT COUNT(DISTINCT domain) FROM businesses WHERE domain != ''").fetchone()[0]
    distinct_postals = verify_conn.execute("SELECT COUNT(DISTINCT postal_code) FROM businesses WHERE postal_code != ''").fetchone()[0]
    distinct_phones = verify_conn.execute("SELECT COUNT(DISTINCT normalized_phone) FROM businesses WHERE normalized_phone != ''").fetchone()[0]
    verify_conn.close()

    print("\n--- Migration Verification Summary ---")
    print(f"Total Businesses in v2:       {total_b}")
    print(f"Total Snapshots in v2:        {total_s}")
    print(f"Total Cases in v2:            {total_c}")
    print(f"Total Submissions in v2:      {total_sub}")
    print(f"Distinct Normalized Domains:  {distinct_domains}")
    print(f"Distinct Dutch Postal Codes:  {distinct_postals}")
    print(f"Distinct Normalized Phones:   {distinct_phones}")
    print("--------------------------------------\n")


if __name__ == "__main__":
    migrate()
