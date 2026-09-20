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
DB_PATH = DATA_DIR / "cases.db"
VIRTUAL_OFFICES_PATH = DATA_DIR / "virtual_offices.json"
PARCEL_CHAINS_PATH = DATA_DIR / "parcel_chains.json"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
DOSSIERS_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

SUBMITTER_NAME = CONFIG.get("submitter_name", DEFAULT_CONFIG["submitter_name"])
SUBMITTER_EMAIL = CONFIG.get("submitter_email", DEFAULT_CONFIG["submitter_email"])
SUBMITTER_ORG = CONFIG.get("submitter_organization", DEFAULT_CONFIG["submitter_organization"])
AUTHUSER = str(CONFIG.get("authuser", DEFAULT_CONFIG["authuser"]))
HEADLESS = bool(CONFIG.get("headless", DEFAULT_CONFIG["headless"]))
USER_AGENT = CONFIG.get("user_agent", DEFAULT_CONFIG["user_agent"])
