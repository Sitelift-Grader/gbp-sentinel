import subprocess
from . import config


def get_forum_url() -> str:
    return f"https://support.google.com/business/thread/new?hl=en&authuser={config.AUTHUSER}"


def build_community_payload(target_name: str, target_kvk: str, target_hq: str, case_id: str, audited_locations: list) -> dict:
    total = len(audited_locations)
    title = f"Escalation request: Case ID {case_id} ({total} locations)"
    body = f"""Dear Product Experts,

I am writing to respectfully request escalation for a formal Business Redressal Complaint submitted under Google Case ID: {case_id}.

The complaint concerns "{target_name}" (KvK: {target_kvk or 'N/A'}), claiming headquarters at {target_hq or 'HQ'}.

A complete audited CSV dossier containing all {total} specific Google Maps URLs, address occupant verifications, and evidence details was attached to Case ID {case_id}.

Summary of policy breaches documented in the dossier:
1. Virtual Offices & Coworking Spaces: Listings registered at unstaffed shared desks and virtual mailboxes without permanent company employees during stated hours.
2. Service Area Business Guidelines: The business provides on-site services at customer locations and does not serve customers at these listed addresses; addresses must be hidden under Google policy.
3. Name Inaccuracies: Artificially inflated profile titles containing geographic and service keywords.

Could a Product Expert please review this complaint and verify if Case ID {case_id} has been escalated to the specialist review team?

Thank you for your time and assistance."""

    return {
        "title": title,
        "body": body,
        "forum_url": get_forum_url()
    }


def copy_to_clipboard(text: str) -> bool:
    try:
        cmd = ["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"]
        p = subprocess.run(cmd, input=text, text=True, encoding="utf-8", check=True)
        return p.returncode == 0
    except Exception as e:
        print(f"Clipboard warning: {e}")
        return False
