"""Configuration for GBP Sentinel."""

import json
from pathlib import Path

# Absolute path to the project root
BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG = {
    "submitter_name": "Trade Compliance Desk",
    "submitter_email": "ddpzonly@gmail.com",
    "submitter_organization": "Local Trade Integrity en Consumer Protection Netherlands",
    "authuser": "1",
    "default_activity_type": "address",
    "headless": True,
    "browser_locale": "nl-NL",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
}

def load_config() -> dict:
    """Load configuration from config.json, falling back to defaults."""
    config = DEFAULT_CONFIG.copy()
    config_path = BASE_DIR / "config.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            config.update(user_config)
        except (json.JSONDecodeError, OSError):
            pass
    return config

CONFIG = load_config()

DATA_DIR = BASE_DIR / "data"
DOSSIERS_DIR = BASE_DIR / "dossiers"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
SCRATCH_DIR = BASE_DIR / "scratch"
DB_PATH = DATA_DIR / "cases.db"
VIRTUAL_OFFICES_PATH = DATA_DIR / "virtual_offices.json"
PARCEL_CHAINS_PATH = DATA_DIR / "parcel_chains.json"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
DOSSIERS_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

SUBMITTER_NAME = CONFIG.get("submitter_name", DEFAULT_CONFIG["submitter_name"])
SUBMITTER_EMAIL = CONFIG.get("submitter_email", DEFAULT_CONFIG["submitter_email"])
SUBMITTER_ORG = CONFIG.get("submitter_organization", DEFAULT_CONFIG["submitter_organization"])
AUTHUSER = str(CONFIG.get("authuser", DEFAULT_CONFIG["authuser"]))
HEADLESS = bool(CONFIG.get("headless", DEFAULT_CONFIG["headless"]))
USER_AGENT = CONFIG.get("user_agent", DEFAULT_CONFIG["user_agent"])

# Canonical Escalation Routing
ROUTING = CONFIG.get("routing", {})
REDRESSAL_FORM_URL = ROUTING.get("redressal_form_url", "https://support.google.com/business/contact/business_redressal_form?hl=en")
GOOGLE_COMMUNITY_URL = ROUTING.get("google_help_community_url", "https://support.google.com/business/thread/new?hl=en")
GOOGLE_COMMUNITY_CATEGORY_EN = ROUTING.get("google_help_category_en", "Policies and guidelines")
GOOGLE_COMMUNITY_CATEGORY_NL = ROUTING.get("google_help_category_nl", "Beleid en richtlijnen")
GOOGLE_COMMUNITY_THREAD_ID = ROUTING.get("google_help_active_thread_id", "469151040")
GOOGLE_COMMUNITY_THREAD_URL = ROUTING.get("google_help_active_thread_url", "https://support.google.com/business/thread/469151040/industrial-google-maps-spam-network-in-netherlands-1-060-fake-listings-73-case-ids")
LSF_POST_URL = ROUTING.get("lsf_post_thread_url", "https://localsearchforum.com/forums/spam-on-google.109/post-thread")
LSF_THREAD_URL = ROUTING.get("lsf_active_thread_url", "https://localsearchforum.com/threads/massive-coordinated-google-maps-spam-syndicate-across-the-netherlands-918-listings-64-redressal-case-ids.63398/")
LSF_TARGET_EXPERT = ROUTING.get("lsf_target_expert", "@keyserholiday")
