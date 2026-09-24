"""Liveness verification engine for Google Business Profile listings.

This module inspects Google Maps place pages directly to determine whether
a listing is still active, converted to a hidden-address SAB, permanently closed,
or completely removed from Google Maps.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import Page, sync_playwright

from . import config, db


def _get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Return a SQLite connection to the locations database."""
    path = db_path or getattr(config, "DB_PATH", getattr(config, "DATABASE_PATH", "data/cases.db"))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Add liveness columns to the locations table if they do not exist."""
    columns = {
        "liveness_status": "TEXT DEFAULT 'untested'",
        "liveness_checked_at": "TEXT",
        "liveness_details": "TEXT",
    }
    for col, definition in columns.items():
        try:
            conn.execute(f"ALTER TABLE locations ADD COLUMN {col} {definition}")
            conn.commit()
        except sqlite3.OperationalError:
            pass


def _update_location(
    loc_id: int,
    status: str,
    details: Dict[str, Any],
    db_path: Optional[str] = None,
) -> None:
    """Update liveness fields for a location row."""
    conn = _get_connection(db_path)
    try:
        _ensure_schema(conn)
        now = datetime.now(timezone.utc).isoformat()
        details_json = json.dumps(details, ensure_ascii=False)
        conn.execute(
            """
            UPDATE locations
            SET liveness_status = ?,
                liveness_checked_at = ?,
                liveness_details = ?
            WHERE id = ?
            """,
            (status, now, details_json, loc_id),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Page inspection helpers
# ---------------------------------------------------------------------------


def _handle_cookie_consent(page: Page) -> bool:
    """Dismiss common Google Maps cookie consent dialogs and wait for navigation."""
    if "consent.google" in page.url or page.locator("button:has-text('Alles accepteren')").count() > 0:
        selectors = [
            "button:has-text('Alles accepteren')",
            "button:has-text('Accept all')",
            "button:has-text('Ik ga akkoord')",
            "button:has-text('Accept all cookies')",
            "button:has-text('Alle cookies accepteren')",
        ]
        for selector in selectors:
            try:
                button = page.locator(selector).first
                if button.is_visible(timeout=2000):
                    button.click(timeout=4000)
                    try:
                        page.wait_for_url("**/maps/**", timeout=15000)
                    except Exception:
                        pass
                    page.wait_for_timeout(3000)
                    return True
            except Exception:
                continue
    return False


def _normalize_name(name: str) -> str:
    """Normalize a place name for comparison."""
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _names_differ(expected: str, actual: str) -> bool:
    """Return True if the actual title differs significantly from expected."""
    if not expected or not actual:
        return False
    exp = _normalize_name(expected)
    act = _normalize_name(actual)
    if not exp or not act:
        return False
    if exp in act or act in exp:
        return False
    exp_tokens = set(exp.split())
    act_tokens = set(act.split())
    if not exp_tokens or not act_tokens:
        return True
    overlap = len(exp_tokens & act_tokens) / max(len(exp_tokens), len(act_tokens))
    return overlap < 0.4


def _get_body_text(page: Page) -> str:
    """Extract visible body text from the page."""
    try:
        return page.locator("body").inner_text(timeout=5000)
    except Exception:
        return ""


def _get_title(page: Page) -> Optional[str]:
    """Extract the place title from the page."""
    selectors = [
        "h1.DUwDvf",
        "h1",
        "[role='main'] h1",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=2000):
                text = locator.inner_text(timeout=2000).strip()
                if text:
                    return text
        except Exception:
            continue
    return None


def _get_address(page: Page) -> Optional[str]:
    """Extract the address from the place card."""
    try:
        locator = page.locator("button[data-item-id='address']").first
        if locator.is_visible(timeout=2000):
            text = locator.inner_text(timeout=2000).strip()
            if text:
                return text
    except Exception:
        pass
    return None


def check_replacement(page: Page, expected_name: str, address: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Search Google Maps to check if a replacement profile was spawned for this business."""
    if not expected_name:
        return None
    search_query = f"{expected_name} {address}" if address else expected_name
    search_query = re.sub(r"[^\w\s]", " ", search_query)
    search_url = f"https://www.google.com/maps/search/{'+'.join(search_query.split())}"
    try:
        page.goto(search_url, timeout=20000, wait_until="domcontentloaded")
        _handle_cookie_consent(page)
        page.wait_for_timeout(2500)

        # Check if single place view opened directly
        title = _get_title(page)
        cur_addr = _get_address(page)

        if title and not _names_differ(expected_name, title):
            return {
                "replacement_found": True,
                "current_title": title,
                "current_address": cur_addr,
                "new_url": page.url,
            }

        # Check if search results list opened
        results = page.locator('a[href*="/maps/place/"]').all()
        for res in results[:3]:
            res_label = res.get_attribute("aria-label") or ""
            if res_label and not _names_differ(expected_name, res_label):
                res.click()
                page.wait_for_timeout(2500)
                cur_title = _get_title(page) or res_label
                cur_addr = _get_address(page)
                return {
                    "replacement_found": True,
                    "current_title": cur_title,
                    "current_address": cur_addr,
                    "new_url": page.url,
                }
    except Exception:
        pass
    return None


def inspect_place(
    page: Page,
    url: str,
    expected_name: Optional[str] = None,
    expected_address: Optional[str] = None,
    timeout_ms: int = 25000,
) -> Dict[str, Any]:
    """Inspect a Google Maps place URL and determine its liveness status."""
    details: Dict[str, Any] = {}
    status = "UNKNOWN"

    try:
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
    except Exception as exc:
        details["navigation_error"] = str(exc)
        return {
            "status": "ERROR",
            "current_title": None,
            "current_address": None,
            "details": details,
            "url": page.url,
        }

    _handle_cookie_consent(page)

    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except Exception:
        pass

    page.wait_for_timeout(1500)
    final_url = page.url
    details["final_url"] = final_url

    # 1. Final URL analysis
    if "/place//@" in final_url or ("/place/" not in final_url and "/@" in final_url):
        status = "REMOVED"
        details["reason"] = "Redirected to empty coordinate map"

    body_text = _get_body_text(page)

    # 2. Body text indicators
    removed_phrases = [
        "kan niet worden gevonden",
        "No results found on Google Maps",
        "Dit profiel is niet meer beschikbaar",
        "Geen resultaten gevonden voor",
    ]
    permanently_closed_phrases = [
        "Permanent gesloten",
        "Permanently closed",
        "Definitief gesloten",
    ]
    temporarily_closed_phrases = [
        "Tijdelijk gesloten",
        "Temporarily closed",
    ]

    if status == "UNKNOWN":
        if any(phrase.lower() in body_text.lower() for phrase in removed_phrases):
            status = "REMOVED"
            details["reason"] = "Body text indicates listing not found"
        elif any(phrase.lower() in body_text.lower() for phrase in permanently_closed_phrases):
            status = "PERMANENTLY_CLOSED"
            details["reason"] = "Body text indicates permanently closed"
        elif any(phrase.lower() in body_text.lower() for phrase in temporarily_closed_phrases):
            status = "TEMPORARILY_CLOSED"
            details["reason"] = "Body text indicates temporarily closed"

    # If removed or empty URL, perform forensic search to see if listing is active on Google Maps
    if (status == "REMOVED" or status == "UNKNOWN") and expected_name:
        active_match = check_replacement(page, expected_name, expected_address)
        if active_match and active_match.get("replacement_found"):
            status = "STILL_ACTIVE"
            details["verified_via_search"] = True
            details["current_url"] = active_match.get("new_url")
            details["current_title"] = active_match.get("current_title")
            details["current_address"] = active_match.get("current_address")
            details["reason"] = (
                f"Listing is active on Google Maps: "
                f"'{active_match.get('current_title')}' at '{active_match.get('current_address')}'"
            )
            return {
                "status": status,
                "current_title": active_match.get("current_title"),
                "current_address": active_match.get("current_address"),
                "details": details,
                "url": active_match.get("new_url") or final_url,
            }
        else:
            status = "CONFIRMED_REMOVED"
            details["reason"] = "Original listing deleted by Google and no active replacement found"
            return {
                "status": status,
                "current_title": None,
                "current_address": None,
                "details": details,
                "url": final_url,
            }

    # 3. Active place card verification
    title = _get_title(page)
    address = _get_address(page)

    if title:
        details["title_found"] = True
        if expected_name and _names_differ(expected_name, title):
            details["title_changed"] = True
            details["expected_name"] = expected_name
            details["current_title"] = title

        if status == "UNKNOWN":
            if address:
                status = "STILL_ACTIVE"
                details["reason"] = f"Address visible: {address}"
            else:
                status = "ACTIVE_ADDRESS_HIDDEN"
                details["reason"] = "Converted to Service Area Business / Address hidden"
    else:
        details["title_found"] = False
        if status == "UNKNOWN":
            status = "UNKNOWN"
            details["reason"] = "No title element found"

    return {
        "status": status,
        "current_title": title,
        "current_address": address,
        "details": details,
        "url": final_url,
    }


# ---------------------------------------------------------------------------
# Batch execution functions
# ---------------------------------------------------------------------------


def check_location(
    loc_id: int,
    page: Optional[Page] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Check a single location by ID and update the database row."""
    conn = _get_connection(db_path)
    _ensure_schema(conn)
    row = conn.execute("SELECT * FROM locations WHERE id = ?", (loc_id,)).fetchone()
    conn.close()

    if row is None:
        raise ValueError(f"Location with id {loc_id} not found")

    data = json.loads(row["data"]) if isinstance(row["data"], str) else (row["data"] or {})
    url = data.get("url") or row.get("url")
    expected_name = data.get("name") or row.get("name")
    expected_address = data.get("address") or row.get("address")

    if not url:
        res = {"status": "ERROR", "details": {"reason": "No URL found in location record"}}
        _update_location(loc_id, "ERROR", res["details"], db_path)
        return res

    if page is not None:
        inspection = inspect_place(page, url, expected_name, expected_address)
    else:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            new_page = browser.new_page(locale="nl-NL")
            try:
                inspection = inspect_place(new_page, url, expected_name, expected_address)
            finally:
                browser.close()

    _update_location(loc_id, inspection["status"], inspection["details"], db_path)
    return inspection


def check_target(
    target_name: str,
    limit: Optional[int] = None,
    headless: bool = True,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Check all locations for a specific target name."""
    conn = _get_connection(db_path)
    _ensure_schema(conn)
    query = "SELECT * FROM locations WHERE target_name = ? ORDER BY id ASC"
    params: list = [target_name]
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = []
    print(f"Checking {len(rows)} locations for target '{target_name}'...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page(locale="nl-NL")
        try:
            for i, row in enumerate(rows, 1):
                loc_id = row["id"]
                data = json.loads(row["data"]) if isinstance(row["data"], str) else (row["data"] or {})
                name = data.get("name", "Unknown")
                print(f"[{i}/{len(rows)}] Loc #{loc_id}: {name[:40]} ...", end=" ", flush=True)
                res = check_location(loc_id, page=page, db_path=db_path)
                results.append({"id": loc_id, "name": name, **res})
                print(f"-> {res['status']}")
        finally:
            browser.close()

    return results


def check_all_locations(
    limit: Optional[int] = None,
    unverified_only: bool = True,
    headless: bool = True,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Check all locations in the database."""
    conn = _get_connection(db_path)
    _ensure_schema(conn)
    query = "SELECT * FROM locations"
    conditions = []
    if unverified_only:
        conditions.append("(liveness_status = 'untested' OR liveness_status IS NULL)")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY id ASC"
    if limit:
        query += f" LIMIT {int(limit)}"
    rows = conn.execute(query).fetchall()
    conn.close()

    results = []
    print(f"Checking {len(rows)} locations across database...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page(locale="nl-NL")
        try:
            for i, row in enumerate(rows, 1):
                loc_id = row["id"]
                data = json.loads(row["data"]) if isinstance(row["data"], str) else (row["data"] or {})
                name = data.get("name", "Unknown")
                print(f"[{i}/{len(rows)}] Loc #{loc_id} ({row['target_name'][:25]}): {name[:30]} ...", end=" ", flush=True)
                res = check_location(loc_id, page=page, db_path=db_path)
                results.append({"id": loc_id, "name": name, **res})
                print(f"-> {res['status']}")
        finally:
            browser.close()

    return results


def print_liveness_summary(db_path: Optional[str] = None) -> None:
    """Print a summary table of liveness statuses."""
    conn = _get_connection(db_path)
    _ensure_schema(conn)
    try:
        total = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
        print("=" * 55)
        print("GOOGLE MAPS LIVENESS VERIFICATION SUMMARY")
        print("=" * 55)
        print(f"Total locations: {total}")
        print("-" * 55)
        print(f"{'Status':<30}{'Count':>10}")
        print("-" * 55)
        rows = conn.execute(
            "SELECT COALESCE(liveness_status, 'untested') AS status, COUNT(*) AS count "
            "FROM locations GROUP BY status ORDER BY count DESC"
        ).fetchall()
        for row in rows:
            print(f"{row['status']:<30}{row['count']:>10}")
        print("=" * 55)
    finally:
        conn.close()


def cli() -> None:
    """Command-line interface for liveness checks."""
    parser = argparse.ArgumentParser(description="Check liveness of locations on Google Maps.")
    parser.add_argument("--target", type=str, help="Check all locations for a specific target name")
    parser.add_argument("--id", type=int, help="Check a single location by ID")
    parser.add_argument("--all", action="store_true", help="Check all locations")
    parser.add_argument("--limit", type=int, help="Limit number of locations to check")
    parser.add_argument("--summary", action="store_true", help="Print liveness summary and exit")
    parser.add_argument("--headful", action="store_true", help="Run browser in headful mode (default headless)")
    parser.add_argument("--db", type=str, default=None, help="Path to SQLite database file")

    args = parser.parse_args()
    db_path = args.db
    headless = not args.headful

    if args.summary:
        print_liveness_summary(db_path)
    elif args.id:
        result = check_location(args.id, db_path=db_path)
        print(f"Location #{args.id}: {result['status']}")
        print(f"  Title:   {result.get('current_title')}")
        print(f"  Address: {result.get('current_address')}")
        print(f"  Details: {result.get('details')}")
    elif args.target:
        results = check_target(args.target, limit=args.limit, headless=headless, db_path=db_path)
        print(f"\nCompleted {len(results)} location checks for '{args.target}'.")
    elif args.all:
        results = check_all_locations(limit=args.limit, unverified_only=False, headless=headless, db_path=db_path)
        print(f"\nCompleted {len(results)} location checks.")
    else:
        parser.print_help()


if __name__ == "__main__":
    cli()
