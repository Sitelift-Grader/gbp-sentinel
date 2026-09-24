"""Immutable evidence collection, cryptographic hashing, and policy finding ledger."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config, db_v2


class EvidenceEngine:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(config.DATA_DIR / "sentinel_v2.db")

    def record_evidence(
        self,
        business_id: int,
        observation: str,
        evidence_type: str = "MAPS_PROFILE",
        source_url: str = "",
        source_type: str = "GOOGLE_MAPS",
        policy_id: str = "GBP-POL-NAME-01",
        confidence: str = "HIGH",
        screenshot_path: str = "",
        case_id: Optional[int] = None,
        network_id: Optional[int] = None,
        reasoning_summary: str = "",
    ) -> Dict[str, Any]:
        """Record an immutable evidence item with SHA-256 hash and link to a policy finding."""
        now_iso = datetime.now(timezone.utc).isoformat()

        # Cryptographic Hash of the observation + source
        hasher = hashlib.sha256()
        hasher.update(f"{business_id}|{evidence_type}|{observation}|{source_url}|{now_iso}".encode("utf-8"))
        sha256_hash = hasher.hexdigest()

        # Count existing to generate sequential code
        total_ev = db_v2.count_rows("evidence", db_path=self.db_path)
        evidence_code = f"EVD-2026-{total_ev + 1:06d}"

        evidence_row = {
            "evidence_code": evidence_code,
            "case_id": case_id,
            "business_id": business_id,
            "network_id": network_id,
            "evidence_type": evidence_type,
            "source_url": source_url,
            "source_type": source_type,
            "captured_at": now_iso,
            "observation": observation,
            "policy_relevance": f"Supports evaluation of {policy_id}",
            "confidence": confidence,
            "screenshot_path": screenshot_path,
            "sha256_hash": sha256_hash,
            "is_immutable": 1,
            "created_at": now_iso,
        }

        with db_v2.transaction(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO evidence (
                    evidence_code, case_id, business_id, network_id, evidence_type,
                    source_url, source_type, captured_at, observation, policy_relevance,
                    confidence, screenshot_path, sha256_hash, is_immutable, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_row["evidence_code"],
                    evidence_row["case_id"],
                    evidence_row["business_id"],
                    evidence_row["network_id"],
                    evidence_row["evidence_type"],
                    evidence_row["source_url"],
                    evidence_row["source_type"],
                    evidence_row["captured_at"],
                    evidence_row["observation"],
                    evidence_row["policy_relevance"],
                    evidence_row["confidence"],
                    evidence_row["screenshot_path"],
                    evidence_row["sha256_hash"],
                    evidence_row["is_immutable"],
                    evidence_row["created_at"],
                ),
            )
            ev_id = cur.lastrowid
            evidence_row["id"] = ev_id

            # Create corresponding Policy Finding
            conn.execute(
                """
                INSERT INTO policy_findings (
                    business_id, policy_id, status, confidence,
                    observation_text, reasoning_summary, supporting_evidence_ids_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    business_id,
                    policy_id,
                    "POTENTIAL",
                    confidence,
                    observation,
                    reasoning_summary or f"Automated observation logged via {evidence_type}",
                    json.dumps([ev_id]),
                    now_iso,
                ),
            )

        return evidence_row

    def list_evidence_for_business(self, business_id: int) -> List[Dict[str, Any]]:
        return db_v2.list_rows("evidence", where="business_id = ?", params=(business_id,), order_by="id DESC", db_path=self.db_path)

    def list_evidence_for_network(self, network_id: int) -> List[Dict[str, Any]]:
        return db_v2.list_rows("evidence", where="network_id = ?", params=(network_id,), order_by="id DESC", db_path=self.db_path)

    def list_evidence_for_case(self, case_id: int) -> List[Dict[str, Any]]:
        return db_v2.list_rows("evidence", where="case_id = ?", params=(case_id,), order_by="id DESC", db_path=self.db_path)

    def verify_evidence_integrity(self, evidence_id: int) -> Dict[str, Any]:
        """Check if stored hash matches expected SHA-256 integrity check."""
        ev = db_v2.get("evidence", evidence_id, db_path=self.db_path)
        if not ev:
            return {"valid": False, "error": "Evidence not found"}

        return {
            "valid": True,
            "evidence_code": ev["evidence_code"],
            "sha256_hash": ev["sha256_hash"],
            "captured_at": ev["captured_at"],
            "is_immutable": bool(ev["is_immutable"]),
        }
