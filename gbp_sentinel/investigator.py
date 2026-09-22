"""Network-level evidence analysis for coordinated GBP policy reports."""

import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from . import config, db


def _normalise_phone(value):
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("31") and len(digits) >= 11:
        digits = "0" + digits[2:]
    return digits if len(digits) >= 9 else ""


def _normalise_website(value):
    hostname = urlparse(value if "://" in (value or "") else f"https://{value or ''}").hostname or ""
    return hostname.lower().removeprefix("www.")


def _normalise_address(value):
    text = re.sub(r"[^a-z0-9]", "", (value or "").lower())
    return "" if text in ("", "addressunverified", "onbekend") else text


def _locations(target_name=None):
    targets = [db.get_target(target_name)] if target_name else db.list_targets()
    for target in targets:
        if not target:
            continue
        for location in db.get_locations(target["name"]):
            yield {"target_name": target["name"], "target_website": target.get("website", ""), **location}


def build_network_report(target_name=None, min_shared=2, output_dir=None):
    """Group profiles by independently repeated public network indicators.

    Shared indicators are leads, not proof of wrongdoing. The report therefore
    keeps every source URL and explicitly separates review-ready evidence from
    older or incomplete data.
    """
    if min_shared < 2:
        raise ValueError("min_shared moet minimaal 2 zijn.")

    records = list(_locations(target_name))
    indicators = defaultdict(list)
    for index, record in enumerate(records):
        values = {
            "phone": _normalise_phone(record.get("phone", "")),
            "website": _normalise_website(record.get("website") or record.get("target_website")),
            "address": _normalise_address(record.get("address", "")),
        }
        for kind, value in values.items():
            if value:
                indicators[(kind, value)].append(index)

    linked = defaultdict(set)
    for key, indexes in indicators.items():
        if len(indexes) >= min_shared:
            for index in indexes:
                linked[index].add(key)

    clusters = []
    visited = set()
    for root in linked:
        if root in visited:
            continue
        pending, component = [root], set()
        while pending:
            current = pending.pop()
            if current in component:
                continue
            component.add(current)
            for signal in linked[current]:
                pending.extend(linked[index] for linked_index in indicators[signal])
        visited.update(component)
        members = [records[index] for index in sorted(component)]
        signals = sorted({f"{kind}:{value}" for index in component for kind, value in linked[index]})
        review_ready = sum(member.get("review_status") == "ready_for_review" for member in members)
        clusters.append({
            "cluster_id": f"cluster-{len(clusters) + 1:03d}",
            "profiles": len(members),
            "targets": sorted({member["target_name"] for member in members}),
            "shared_indicators": signals,
            "review_ready_profiles": review_ready,
            "requires_manual_review": review_ready != len(members),
            "maps_urls": [member.get("url", "") for member in members if member.get("url")],
            "members": members,
        })

    clusters.sort(key=lambda cluster: (cluster["profiles"], len(cluster["shared_indicators"])), reverse=True)
    report_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_dir = Path(output_dir) if output_dir else config.DOSSIERS_DIR / "investigations" / report_id
    report_dir.mkdir(parents=True, exist_ok=False)

    manifest = {
        "report_id": report_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": target_name or "all_targets",
        "source_profiles": len(records),
        "minimum_shared_indicator_count": min_shared,
        "notice": "Shared public indicators are investigation leads, not a conclusion of fraud.",
        "clusters": clusters,
    }
    manifest_path = report_dir / "network_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    queue_path = report_dir / "cluster_review_queue.csv"
    with queue_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["cluster_id", "profiles", "targets", "review_ready_profiles", "requires_manual_review", "shared_indicators"])
        writer.writeheader()
        for cluster in clusters:
            writer.writerow({
                "cluster_id": cluster["cluster_id"],
                "profiles": cluster["profiles"],
                "targets": " | ".join(cluster["targets"]),
                "review_ready_profiles": cluster["review_ready_profiles"],
                "requires_manual_review": cluster["requires_manual_review"],
                "shared_indicators": " | ".join(cluster["shared_indicators"]),
            })
    return manifest_path, manifest


def build_follow_up_queue(days=7, output_dir=None):
    """Prepare a manual status-check queue for cases that may need follow-up."""
    if days < 1:
        raise ValueError("Aantal dagen moet minimaal 1 zijn.")
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
    candidates = []
    for submission in db.list_submissions():
        if submission.get("status", "").lower() not in {"submitted", "awaiting_google_review", "follow_up_sent"}:
            continue
        try:
            created = datetime.fromisoformat(submission["created_at"]).timestamp()
        except (KeyError, TypeError, ValueError):
            created = 0
        if created <= cutoff:
            candidates.append(submission)

    report_dir = Path(output_dir) if output_dir else config.DOSSIERS_DIR / "follow_up"
    report_dir.mkdir(parents=True, exist_ok=True)
    queue_path = report_dir / f"case_follow_up_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
    with queue_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["case_id", "target_name", "created_at", "status", "dossier_path", "result_screenshot"])
        writer.writeheader()
        writer.writerows({key: item.get(key, "") for key in writer.fieldnames} for item in candidates)
    return queue_path, candidates
