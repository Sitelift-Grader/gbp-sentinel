"""Canonical escalation routing and community payloads for GBP Sentinel."""

import subprocess
import sys
from typing import List, Optional

from . import config


def get_forum_url() -> str:
    """Return the canonical Google Business Profile Help Community URL for new threads."""
    return f"{config.GOOGLE_COMMUNITY_URL}&authuser={config.AUTHUSER}"


def build_community_payload(
    target_name: str,
    case_id: str,
    audited_locations: list,
    summary_text: Optional[str] = None,
) -> dict:
    """Construct a standardized payload for the Google Help Community.
    
    Strictly specifies the required Category ('Policies and guidelines') to ensure
    Google Product Experts can escalate directly to Google Trust & Safety.
    """
    total = len(audited_locations)
    title = f"Industrial Google Maps Spam: {target_name} ({total} locs, Case ID {case_id})"
    if len(title) > 98:
        title = title[:95] + "..."

    body = f"""Dear Google Product Experts and Trust & Safety Team,

I am requesting escalation for a coordinated Google Maps lead-generation network operating in the Netherlands under official Google Case ID: {case_id}.

Target Syndicate: {target_name}
Verified Fraudulent Locations: {total}

Reference Master Thread on Local Search Forum:
{config.LSF_THREAD_URL}

Summary of Documented Policy Violations:
1. Virtual Offices & Flex Hubs (Guideline 2447164): Claiming physical storefronts, workshops, and trade facilities at unstaffed commercial business centers (e.g. Regus Sloterdijk, Regus Weena, Regus World Forum) with zero staff, stock, equipment, or vehicles on site.
2. Third-Party Drop-off & Partner Hijacking: Claiming independent third-party auto repair shops, retail stores, or partner locations without dedicated storefronts or staff.
3. Consecutive VoIP SIP Blocks: Sequential phone numbers routing to an unlicensed central call broker.
4. Systematic Title Manipulation (Guideline 3052070): Keyword stuffing and location spam across Dutch municipalities.

A complete audited CSV dossier containing all {total} specific Google Maps URLs, address occupant verifications, and evidence details was attached to Google Case ID {case_id}.

Could a Diamond or Platinum Product Expert please review and escalate Case ID {case_id} to Google Trust & Safety Spam Engineering for network-level manual action?

Thank you for your assistance in protecting consumers from deceptive lead brokerage."""

    if summary_text:
        body += f"\n\nAdditional Evidence Details:\n{summary_text}"

    return {
        "title": title,
        "category_en": config.GOOGLE_COMMUNITY_CATEGORY_EN,
        "category_nl": config.GOOGLE_COMMUNITY_CATEGORY_NL,
        "body": body,
        "forum_url": get_forum_url(),
        "active_thread_url": config.GOOGLE_COMMUNITY_THREAD_URL,
        "active_thread_id": config.GOOGLE_COMMUNITY_THREAD_ID,
    }


def build_lsf_cross_reply(
    google_thread_url: str = None,
    case_ids: Optional[List[str]] = None,
) -> str:
    """Build a courteous reply message for Local Search Forum tagging @keyserholiday."""
    thread_url = google_thread_url or config.GOOGLE_COMMUNITY_THREAD_URL
    thread_id = config.GOOGLE_COMMUNITY_THREAD_ID

    reply = f"""Hi {config.LSF_TARGET_EXPERT},

Thank you for the guidance! As requested, I have created the official escalation thread on the Google Business Profile Help Community:

Thread URL: {thread_url}
Thread ID: {thread_id}

(Note: Google's automated filter may place comprehensive multi-case dossiers in the community queue awaiting PE / moderation approval)."""

    if case_ids:
        reply += f"\n\nAssociated Google Redressal Case IDs:\n" + "\n".join(f"- {cid}" for cid in case_ids)

    reply += f"""

We would be immensely grateful if you could pull it up in the PE console and escalate it directly to Google Trust & Safety Spam Engineering for network-level manual action.

Thank you so much for your assistance!"""
    return reply


def copy_to_clipboard(text: str) -> bool:
    """Copy given text to Windows clipboard using PowerShell."""
    try:
        cmd = ["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"]
        p = subprocess.run(cmd, input=text, text=True, encoding="utf-8", check=True)
        return p.returncode == 0
    except Exception as e:
        print(f"Clipboard warning: {e}")
        return False
