"""Monitoring, differential snapshot inspection, and network reincarnation detection."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config, db_v2, normalizer


class MonitoringEngine:
    VALID_OUTCOMES = frozenset({
        "UNKNOWN",
        "NO_VISIBLE_CHANGE",
        "PROFILE_CHANGED",
        "PROFILE_REMOVED",
        "PROFILE_SUSPENDED",
        "PROFILE_MERGED",
        "DUPLICATE_REMOVED",
        "TEMPORARILY_UNAVAILABLE",
    })

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(config.DATA_DIR / "sentinel_v2.db")

    def capture_snapshot(self, business_id: int, fresh_data: Dict[str, Any]) -> Dict[str, Any]:
        """Record fresh observation snapshot and detect field diffs against prior snapshot."""
        biz = db_v2.get("businesses", business_id, db_path=self.db_path)
        if not biz:
            raise ValueError(f"Business {business_id} not found.")

        now_iso = datetime.now(timezone.utc).isoformat()
        raw_json = json.dumps(fresh_data, ensure_ascii=False)
        sha_hash = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

        # Get latest snapshot
        latest = db_v2.list_rows(
            "business_snapshots",
            where="business_id = ?",
            params=(business_id,),
            order_by="snapshot_timestamp DESC",
            limit=1,
            db_path=self.db_path,
        )

        diffs = []
        if latest:
            old = latest[0]
            for field in ("name", "address", "phone", "website", "category", "status_visible"):
                old_val = old.get(field) or ""
                new_val = fresh_data.get(field) or ""
                if old_val and new_val and old_val.lower() != new_val.lower():
                    diffs.append({
                        "field": field,
                        "old_value": old_val,
                        "new_value": new_val,
                        "event_type": f"{field.upper()}_CHANGED",
                    })

        with db_v2.transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO business_snapshots (
                    business_id, snapshot_timestamp, name, address, phone,
                    website, category, status_visible, raw_payload_json, sha256_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    business_id,
                    now_iso,
                    fresh_data.get("name", biz.get("name")),
                    fresh_data.get("address", biz.get("address")),
                    fresh_data.get("phone", biz.get("phone")),
                    fresh_data.get("website", biz.get("domain")),
                    fresh_data.get("category", biz.get("category")),
                    fresh_data.get("status_visible", "ACTIVE"),
                    raw_json,
                    sha_hash,
                ),
            )

            # Record monitoring events for diffs
            for d in diffs:
                conn.execute(
                    """
                    INSERT INTO monitoring_events (
                        business_id, event_type, previous_val, new_val, description, occurred_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        business_id,
                        d["event_type"],
                        d["old_value"],
                        d["new_value"],
                        f"Detected change in {d['field']} during monitoring sweep",
                        now_iso,
                    ),
                )

        return {"business_id": business_id, "snapshot_timestamp": now_iso, "diffs": diffs}

    def record_outcome(
        self,
        case_id: int,
        business_id: int,
        outcome_type: str,
        description: str = "",
        screenshot_proof_path: str = "",
    ) -> Dict[str, Any]:
        """Record verified Google-visible outcome for a reported case."""
        if outcome_type not in self.VALID_OUTCOMES:
            raise ValueError(f"Invalid outcome: {outcome_type}. Allowed: {sorted(self.VALID_OUTCOMES)}")

        now_iso = datetime.now(timezone.utc).isoformat()
        outcome_data = {
            "case_id": case_id,
            "business_id": business_id,
            "outcome_type": outcome_type,
            "description": description or f"Outcome verified as {outcome_type}",
            "verified_at": now_iso,
            "screenshot_proof_path": screenshot_proof_path,
        }

        with db_v2.transaction(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO outcomes (case_id, business_id, outcome_type, description, verified_at, screenshot_proof_path)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    case_id,
                    business_id,
                    outcome_type,
                    outcome_data["description"],
                    now_iso,
                    screenshot_proof_path,
                ),
            )
            outcome_data["id"] = cur.lastrowid

            # If profile removed, update case status to ACTION_OBSERVED
            if outcome_type in ("PROFILE_REMOVED", "PROFILE_SUSPENDED", "DUPLICATE_REMOVED"):
                conn.execute(
                    "UPDATE cases SET status = 'ACTION_OBSERVED', updated_at = ? WHERE id = ?",
                    (now_iso, case_id),
                )

        return outcome_data

    def detect_reincarnation(self, network_id: int) -> List[Dict[str, Any]]:
        """Look for newly appeared listings matching infrastructure of removed/suspended profiles.

        Identifies: 'Possible network recurrence' (not 'ban evasion confirmed').
        """
        # Find removed businesses in this network
        removed_bizs = db_v2.list_rows(
            "businesses",
            where="""
            id IN (
                SELECT b.id FROM businesses b
                JOIN network_members nm ON b.id = nm.business_id
                JOIN outcomes o ON b.id = o.business_id
                WHERE nm.network_id = ? AND o.outcome_type IN ('PROFILE_REMOVED', 'PROFILE_SUSPENDED')
            )
            """,
            params=(network_id,),
            db_path=self.db_path,
        )

        if not removed_bizs:
            return []

        reincarnation_signals = []
        for r_biz in removed_bizs:
            phone = r_biz.get("normalized_phone")
            domain = r_biz.get("domain")
            postal = r_biz.get("postal_code")

            # Look for active/new businesses sharing this exact infrastructure
            where_clauses = []
            params = []
            if phone:
                where_clauses.append("normalized_phone = ?")
                params.append(phone)
            if domain:
                where_clauses.append("domain = ?")
                params.append(domain)
            if postal:
                where_clauses.append("postal_code = ?")
                params.append(postal)

            if not where_clauses:
                continue

            query = f"id != ? AND ({' OR '.join(where_clauses)})"
            all_params = tuple([r_biz["id"]] + params)

            matches = db_v2.list_rows("businesses", where=query, params=all_params, db_path=self.db_path)
            for m in matches:
                reincarnation_signals.append({
                    "historical_removed_business": r_biz.get("name"),
                    "removed_id": r_biz["id"],
                    "candidate_recurrent_business": m.get("name"),
                    "candidate_id": m["id"],
                    "shared_phone": bool(phone and phone == m.get("normalized_phone")),
                    "shared_domain": bool(domain and domain == m.get("domain")),
                    "shared_address": bool(postal and postal == m.get("postal_code")),
                    "signal_label": "Possible network recurrence",
                    "note": "Further manual verification required before concluding deliberate profile reincarnation.",
                })

        return reincarnation_signals
