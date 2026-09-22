"""Evidence-gated batch preparation for coordinated GBP policy reports."""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from . import db, dossier


ROUTES = {
    "virtual_office": "google_redressal",
    "parcel_dropoff": "google_redressal",
    "keyword_stuffing": "maps_edit_then_redressal",
    "residential": "maps_edit_then_redressal",
}


def _reportable_locations(target_name=None):
    """Return only locations that have passed the evidence gate."""
    targets = [db.get_target(target_name)] if target_name else db.list_targets()
    locations = []
    for target in targets:
        if not target:
            continue
        for location in db.get_locations(target["name"]):
            if location.get("review_status") != "ready_for_review":
                continue
            if not location.get("is_reportable"):
                continue
            locations.append({"target_name": target["name"], **location})
    return locations


def build_campaign(target_name=None, batch_size=20, output_dir=None):
    """Create CSV batches and a manifest without contacting external services."""
    if batch_size < 1 or batch_size > 100:
        raise ValueError("Batchgrootte moet tussen 1 en 100 liggen.")

    locations = _reportable_locations(target_name)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    campaign_dir = Path(output_dir) if output_dir else dossier.config.DOSSIERS_DIR / "campaigns" / timestamp
    campaign_dir.mkdir(parents=True, exist_ok=False)

    grouped = {}
    for location in locations:
        category = location.get("violation_category", "needs_review")
        grouped.setdefault(category, []).append(location)

    batches = []
    for category, grouped_locations in sorted(grouped.items()):
        for index in range(0, len(grouped_locations), batch_size):
            chunk = grouped_locations[index:index + batch_size]
            batch_number = (index // batch_size) + 1
            batch_id = f"{category}-{batch_number:03d}"
            csv_path = dossier.export_dossier_csv(
                batch_id,
                chunk,
                filename=f"{batch_id}.csv",
                output_dir=campaign_dir,
            )
            batches.append({
                "batch_id": batch_id,
                "route": ROUTES.get(category, "manual_review"),
                "violation_category": category,
                "locations": len(chunk),
                "csv_path": str(csv_path),
                "maps_urls": [location.get("url", "") for location in chunk],
                "evidence_signals": sorted({signal for location in chunk for signal in location.get("evidence_signals", [])}),
                "status": "ready_for_human_submission",
            })

    manifest = {
        "campaign_id": timestamp,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": target_name or "all_targets",
        "total_review_ready_locations": len(locations),
        "submission_policy": "No external report is sent by this command. Review each batch before submitting.",
        "batches": batches,
    }
    manifest_path = campaign_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    queue_path = campaign_dir / "submission_queue.csv"
    with queue_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["batch_id", "route", "violation_category", "locations", "csv_path", "status"])
        writer.writeheader()
        writer.writerows({key: batch[key] for key in writer.fieldnames} for batch in batches)

    return manifest_path, manifest
