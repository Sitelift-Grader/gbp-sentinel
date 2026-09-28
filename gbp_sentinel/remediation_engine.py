from __future__ import annotations

import asyncio
from typing import Any
from . import db
from .name_sanitizer import NameSanitizer
from .maps_editor import MapsEditor
from .submitter import RedressalSubmitter


class RemediationEngine:
    """
    Centrale orchestrator voor profielsanering en keyword stuffing aanpak.
    Verbindt NameSanitizer, MapsEditor en RedressalSubmitter.
    """

    def __init__(self, headless: bool = True):
        self.sanitizer = NameSanitizer()
        self.editor = MapsEditor(headless=headless)
        self.redressal = RedressalSubmitter(headless=headless)
        db.init_db()

    def process_listing(self, listing: dict[str, Any], auto_save: bool = True) -> dict[str, Any]:
        """
        Analyseert een individuele vermelding en bepaalt de juiste saneringsactie.
        """
        title = listing.get("title") or listing.get("name") or ""
        url = listing.get("url") or ""
        web = listing.get("website") or ""
        addr = listing.get("address") or ""

        analysis = self.sanitizer.sanitize(raw_title=title, website_url=web, address=addr)
        action = analysis["action"]
        clean_name = analysis["clean_name"]

        edit_id = None
        if auto_save and action in ("RENAME", "REMOVE"):
            track = "MAPS_EDIT" if action == "RENAME" else "REDRESSAL"
            notes = "; ".join(analysis["reasons"])
            edit_id = db.save_profile_edit(
                place_url=url,
                original_title=title,
                sanitized_title=clean_name if action == "RENAME" else "[VERWIJDERING GEVRAAGD]",
                action_type=action,
                remediation_track=track,
                status="proposed",
                notes=notes
            )

        return {
            "edit_id": edit_id,
            "place_url": url,
            "original_title": title,
            "action": action,
            "clean_name": clean_name,
            "confidence": analysis["confidence"],
            "removed_parts": analysis["removed_parts"],
            "reasons": analysis["reasons"]
        }

    def process_batch(self, listings: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Verwerkt een batch van vermeldingen en categoriseert ze in RENAME, REMOVE en KEEP.
        """
        summary = {
            "total": len(listings),
            "renames": [],
            "removals": [],
            "kept": []
        }

        for loc in listings:
            res = self.process_listing(loc, auto_save=True)
            if res["action"] == "RENAME":
                summary["renames"].append(res)
            elif res["action"] == "REMOVE":
                summary["removals"].append(res)
            else:
                summary["kept"].append(res)

        return summary

    async def execute_maps_edit(self, edit_id: int) -> dict[str, Any]:
        """
        Voert een eerder opgeslagen naamsbewerking uit op Google Maps.
        """
        conn = db._get_connection()
        try:
            row = conn.execute("SELECT * FROM profile_edits WHERE id = ?", (edit_id,)).fetchone()
            if not row:
                return {"status": "error", "message": f"Edit ID {edit_id} niet gevonden"}

            res = await self.editor.suggest_name_edit(
                place_url=row["place_url"],
                new_name=row["sanitized_title"],
                edit_id=edit_id
            )

            status = res.get("status", "failed")
            db.update_profile_edit_status(
                edit_id=edit_id,
                status=status,
                notes=f"Maps submit: {res.get('error', 'ok')}"
            )
            return res
        finally:
            conn.close()
