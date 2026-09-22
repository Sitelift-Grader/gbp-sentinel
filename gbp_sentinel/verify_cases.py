"""Verification workflow helpers for GBP Sentinel."""
import sqlite3
import argparse
from datetime import datetime

from . import config, db

VALID_GOOGLE_STATUSES = {
    "pending_email_verification",
    "verified",
    "under_review",
    "resolved",
    "rejected",
    "action_taken",
}


def _connect(db_path=None):
    """Return a SQLite connection for the configured database."""
    path = db_path or getattr(config, "DB_PATH", getattr(config, "DATABASE_PATH", "data/cases.db"))
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _serialize_row(row):
    """Convert a sqlite3.Row to a plain dict."""
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def list_pending_cases(db_path=None):
    """Fetch all submissions awaiting email verification."""
    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT case_id, target_name, email, created_at, google_status AS status
            FROM submissions
            WHERE email_verified = 0 OR google_status = 'pending_email_verification'
            ORDER BY created_at DESC
            """
        )
        rows = cursor.fetchall()
        return [_serialize_row(row) for row in rows]
    finally:
        conn.close()


def mark_case_verified(case_id, db_path=None):
    """Mark a single case as email verified."""
    conn = _connect(db_path)
    try:
        now = datetime.now().isoformat()
        cursor = conn.execute(
            """
            UPDATE submissions
            SET email_verified = 1,
                verified_at = ?,
                google_status = 'verified'
            WHERE case_id = ?
            """,
            (now, str(case_id)),
        )
        conn.commit()
        updated = cursor.rowcount > 0
        if updated:
            db.save_case_event(
                str(case_id),
                "email_verified",
                "User confirmed verification link in email",
            )
        return updated
    finally:
        conn.close()


def mark_all_cases_verified(db_path=None):
    """Mark every unverified submission as email verified.

    Returns the number of cases updated.
    """
    conn = _connect(db_path)
    try:
        now = datetime.now().isoformat()
        cursor = conn.execute(
            "SELECT case_id FROM submissions WHERE email_verified = 0 OR email_verified IS NULL"
        )
        case_ids = [row["case_id"] for row in cursor.fetchall()]

        if not case_ids:
            return 0

        placeholders = ",".join("?" for _ in case_ids)
        conn.execute(
            f"""
            UPDATE submissions
            SET email_verified = 1,
                verified_at = ?,
                google_status = 'verified'
            WHERE case_id IN ({placeholders})
            """,
            (now, *case_ids),
        )
        conn.commit()

        for cid in case_ids:
            db.save_case_event(
                cid,
                "email_verified",
                "User confirmed verification link in email",
            )

        return len(case_ids)
    finally:
        conn.close()


def update_google_status(case_id, new_status, details="", db_path=None):
    """Update the Google status for a case and record an event."""
    if new_status not in VALID_GOOGLE_STATUSES:
        raise ValueError(
            f"Invalid Google status: {new_status}. "
            f"Valid options: {', '.join(sorted(VALID_GOOGLE_STATUSES))}"
        )

    conn = _connect(db_path)
    try:
        now = datetime.now().isoformat()
        cursor = conn.execute(
            """
            UPDATE submissions
            SET google_status = ?,
                last_checked_at = ?
            WHERE case_id = ?
            """,
            (new_status, now, str(case_id)),
        )
        conn.commit()
        updated = cursor.rowcount > 0
        if updated:
            event_details = details or f"Status changed to {new_status}"
            db.save_case_event(str(case_id), f"google_status_{new_status}", event_details)
        return updated
    finally:
        conn.close()


def print_summary(db_path=None):
    """Print a verification summary table."""
    conn = _connect(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) AS c FROM submissions").fetchone()["c"]

        verified_count = conn.execute(
            "SELECT COUNT(*) AS c FROM submissions WHERE email_verified = 1"
        ).fetchone()["c"]

        pending_count = total - verified_count

        print("=" * 65)
        print("GOOGLE SUBMISSION & EMAIL VERIFICATION SUMMARY")
        print("=" * 65)
        print(f"Total submissions          : {total}")
        print(f"Email verified             : {verified_count}")
        print(f"Pending email verification : {pending_count}")
        print("-" * 65)
        print("Breakdown by google_status:")
        print(f"{'Status':<35}{'Count':>8}")
        print("-" * 65)

        rows = conn.execute(
            "SELECT COALESCE(google_status, '(unset)') AS google_status, COUNT(*) AS count "
            "FROM submissions GROUP BY google_status ORDER BY count DESC"
        ).fetchall()
        if not rows:
            print(f"{'(none)':<35}{0:>8}")
        for row in rows:
            print(f"{row['google_status']:<35}{row['count']:>8}")

        print("=" * 65)
    finally:
        conn.close()


def cli():
    """Command-line entrypoint for verification tooling."""
    parser = argparse.ArgumentParser(
        description="Manage and inspect GBP submission verification status."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all pending cases awaiting email verification",
    )
    parser.add_argument(
        "--verify-all",
        action="store_true",
        help="Mark all unverified cases as email verified",
    )
    parser.add_argument(
        "--verify",
        metavar="CASE_ID",
        type=str,
        help="Mark a single case as email verified",
    )
    parser.add_argument(
        "--status",
        nargs=2,
        metavar=("CASE_ID", "NEW_STATUS"),
        help="Update the Google status for a case",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a verification summary",
    )

    args = parser.parse_args()

    if args.list:
        cases = list_pending_cases()
        if not cases:
            print("No pending cases found.")
        else:
            print(f"{'Case ID':<22}{'Target Name':<45}{'Email':<25}{'Status'}")
            print("-" * 110)
            for case in cases:
                print(
                    f"{case['case_id']:<22}"
                    f"{case['target_name'][:43]:<45}"
                    f"{case['email']:<25}"
                    f"{case['status'] or 'pending_email_verification'}"
                )
            print("-" * 110)
            print(f"Total pending email verification: {len(cases)}")
    elif args.verify_all:
        count = mark_all_cases_verified()
        print(f"Marked {count} case(s) as email verified.")
    elif args.verify is not None:
        success = mark_case_verified(args.verify)
        if success:
            print(f"Case {args.verify} marked as email verified.")
        else:
            print(f"Case {args.verify} not found or no update performed.")
    elif args.status:
        case_id, status = args.status
        try:
            success = update_google_status(case_id, status)
        except ValueError as exc:
            parser.error(str(exc))
        if success:
            print(f"Case {case_id} Google status updated to '{status}'.")
        else:
            print(f"Case {case_id} not found or no update performed.")
    elif args.summary:
        print_summary()
    else:
        parser.print_help()


if __name__ == "__main__":
    cli()
