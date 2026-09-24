"""Case management and human-in-the-loop review queue for GBP SMOKER / Sentinel."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config, db_v2


VALID_CASE_STATUSES = frozenset({
    "DISCOVERED",
    "INVESTIGATING",
    "EVIDENCE_COLLECTED",
    "NEEDS_REVIEW",
    "APPROVED",
    "REPORTED",
    "ACKNOWLEDGED",
    "ACTION_OBSERVED",
    "NO_ACTION_OBSERVED",
    "CLOSED",
    "MONITORING",
})


class CaseManager:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(config.DATA_DIR / "sentinel_v2.db")

    def create_case(
        self,
        title: str,
        network_id: Optional[int] = None,
        business_ids: Optional[List[int]] = None,
        priority: str = "MEDIUM",
        reviewer_name: str = "Compliance Officer",
        notes: str = "",
    ) -> Dict[str, Any]:
        """Create a new investigative case grouping businesses and/or a network."""
        now_iso = datetime.now(timezone.utc).isoformat()
        total_cases = db_v2.count_rows("cases", db_path=self.db_path)
        case_code = f"CASE-2026-{total_cases + 1:06d}"

        case_data = {
            "case_code": case_code,
            "network_id": network_id,
            "title": title,
            "priority": priority,
            "status": "DISCOVERED",
            "reviewer_name": reviewer_name,
            "notes": notes,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        with db_v2.transaction(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO cases (
                    case_code, network_id, title, priority, status, reviewer_name, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case_data["case_code"],
                    case_data["network_id"],
                    case_data["title"],
                    case_data["priority"],
                    case_data["status"],
                    case_data["reviewer_name"],
                    case_data["notes"],
                    case_data["created_at"],
                    case_data["updated_at"],
                ),
            )
            case_id = cur.lastrowid
            case_data["id"] = case_id

            if business_ids:
                for b_id in business_ids:
                    conn.execute(
                        "INSERT OR IGNORE INTO case_businesses (case_id, business_id, role) VALUES (?, ?, ?)",
                        (case_id, b_id, "SUBJECT"),
                    )

        return case_data

    def update_case_status(
        self, case_id: int, status: str, notes: str = "", reviewer: str = ""
    ) -> bool:
        if status not in VALID_CASE_STATUSES:
            raise ValueError(f"Invalid status: {status}. Allowed: {sorted(VALID_CASE_STATUSES)}")

        now_iso = datetime.now(timezone.utc).isoformat()
        update_data = {"status": status, "updated_at": now_iso}
        if notes:
            update_data["notes"] = notes
        if reviewer:
            update_data["reviewer_name"] = reviewer

        return db_v2.update("cases", case_id, update_data, db_path=self.db_path)

    def review_finding(
        self,
        finding_id: int,
        reviewer: str,
        action: str,  # 'APPROVE' or 'REJECT'
        dismissal_reason: str = "",
        context_notes: str = "",
        case_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Human-in-the-loop review of a finding. If rejected, logs to false_positive_logs."""
        finding = db_v2.get("policy_findings", finding_id, db_path=self.db_path)
        if not finding:
            raise ValueError(f"Finding {finding_id} not found.")

        business_id = finding["business_id"]
        now_iso = datetime.now(timezone.utc).isoformat()

        with db_v2.transaction(self.db_path) as conn:
            new_status = "VERIFIED" if action == "APPROVE" else "REJECTED"
            conn.execute(
                "UPDATE policy_findings SET status = ? WHERE id = ?",
                (new_status, finding_id),
            )

            conn.execute(
                """
                INSERT INTO review_actions (case_id, business_id, finding_id, reviewer, action, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (case_id, business_id, finding_id, reviewer, action, dismissal_reason, now_iso),
            )

            if action == "REJECT":
                conn.execute(
                    """
                    INSERT INTO false_positive_logs (business_id, finding_id, reviewer, dismissal_reason, context_notes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (business_id, finding_id, reviewer, dismissal_reason or "Marked as non-violating by reviewer", context_notes, now_iso),
                )

        return {
            "finding_id": finding_id,
            "status": new_status,
            "reviewer": reviewer,
            "action": action,
            "dismissal_reason": dismissal_reason,
        }

    def get_case_summary(self, case_id: int) -> Dict[str, Any]:
        """Fetch comprehensive details, businesses, evidence, and submissions for a case."""
        case = db_v2.get("cases", case_id, db_path=self.db_path)
        if not case:
            return {}

        businesses = db_v2.list_rows(
            "businesses",
            where="id IN (SELECT business_id FROM case_businesses WHERE case_id = ?)",
            params=(case_id,),
            db_path=self.db_path,
        )

        evidence = db_v2.list_rows("evidence", where="case_id = ?", params=(case_id,), db_path=self.db_path)
        submissions = db_v2.list_rows("submissions", where="case_id = ?", params=(case_id,), db_path=self.db_path)
        outcomes = db_v2.list_rows("outcomes", where="case_id = ?", params=(case_id,), db_path=self.db_path)

        return {
            "case": case,
            "businesses": businesses,
            "businesses_count": len(businesses),
            "evidence": evidence,
            "evidence_count": len(evidence),
            "submissions": submissions,
            "outcomes": outcomes,
        }
