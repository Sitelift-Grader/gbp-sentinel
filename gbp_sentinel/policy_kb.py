from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Optional


@dataclass(frozen=True)
class GbpPolicyRecord:
    policy_id: str
    category: str
    title: str
    description: str
    official_source_url: str
    source_date: str
    last_verified: str
    severity: str
    applicable_to: list[str]
    examples: list[str]
    counter_examples: list[str]

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("policy_id must not be empty")
        if not self.category.strip():
            raise ValueError("category must not be empty")
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if not self.description.strip():
            raise ValueError("description must not be empty")
        if not self.official_source_url.startswith("https://support.google.com/"):
            raise ValueError("official_source_url must be an official Google Support URL")
        for field_name in ("source_date", "last_verified"):
            value = getattr(self, field_name)
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"{field_name} must be an ISO-8601 date") from exc
        if self.severity not in {"CRITICAL", "HIGH", "MEDIUM"}:
            raise ValueError("severity must be CRITICAL, HIGH, or MEDIUM")
        for field_name in ("applicable_to", "examples", "counter_examples"):
            value = getattr(self, field_name)
            if not isinstance(value, list) or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                raise ValueError(f"{field_name} must be a list of non-empty strings")


class GbpPolicyKB:
    """Versioned local knowledge base for Google Business Profile policies."""

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS policies (
            policy_id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            official_source_url TEXT NOT NULL,
            source_date TEXT NOT NULL,
            last_verified TEXT NOT NULL,
            severity TEXT NOT NULL,
            applicable_to_json TEXT NOT NULL,
            examples_json TEXT NOT NULL,
            counter_examples_json TEXT NOT NULL
        )
    """

    def __init__(self, db_path: str | Path | None = None):
        self._lock = threading.RLock()
        self._owns_connection = True
        if db_path is None:
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        elif isinstance(db_path, sqlite3.Connection):
            self._conn = db_path
            self._owns_connection = False
        else:
            path = str(db_path)
            if path != ":memory:":
                Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._initialize()
        self.seed_db()

    def _initialize(self) -> None:
        with self._lock:
            self._conn.execute(self._SCHEMA)
            self._conn.commit()

    @staticmethod
    def load_default_policies() -> list[GbpPolicyRecord]:
        source_date = "2026-01-15"
        last_verified = "2026-09-01"
        return [
            GbpPolicyRecord(
                policy_id="GBP-POL-NAME-01",
                category="Business name guidelines",
                title="Use the real-world business name",
                description=(
                    "A Business Profile name must accurately reflect the name used by the "
                    "business in the real world, as represented by signage, stationery, "
                    "branding, and customers. Do not add unnecessary information such as "
                    "marketing taglines, services, products, locations, phone numbers, "
                    "hours, or keywords."
                ),
                official_source_url="https://support.google.com/business/answer/3038177",
                source_date=source_date,
                last_verified=last_verified,
                severity="HIGH",
                applicable_to=["all_businesses", "storefronts", "service_area_businesses"],
                examples=[
                    "Acme Plumbing",
                    "Northside Dental",
                    "The Green Grocer",
                ],
                counter_examples=[
                    "Acme Plumbing - 24/7 Emergency Plumber Best Prices",
                    "Northside Dental Dentist New York",
                    "The Green Grocer - Organic Food Delivery - Call 555-0100",
                ],
            ),
            GbpPolicyRecord(
                policy_id="GBP-POL-ADDR-01",
                category="Address and location requirements",
                title="Use an accurate, eligible business location",
                description=(
                    "A business may show a storefront address only when it makes in-person "
                    "contact with customers at that location during stated hours. The "
                    "address must be accurate and represent the business location; "
                    "mailboxes, remote mail drops, and other ineligible addresses must "
                    "not be used as a storefront location."
                ),
                official_source_url="https://support.google.com/business/answer/3038177",
                source_date=source_date,
                last_verified=last_verified,
                severity="CRITICAL",
                applicable_to=["storefronts", "hybrid_businesses", "service_area_businesses"],
                examples=[
                    "A staffed retail shop with permanent signage and customer access",
                    "A clinic where patients are seen at the published address",
                    "A contractor hiding the street address when customers are not served there",
                ],
                counter_examples=[
                    "A home address presented as a walk-in office when no customer visits occur",
                    "A virtual mailbox used as the business location",
                    "A coworking address used without a dedicated staffed office and signage",
                ],
            ),
            GbpPolicyRecord(
                policy_id="GBP-POL-SAB-01",
                category="Service-area businesses",
                title="Service-area businesses must serve customers at their locations",
                description=(
                    "A service-area business travels to customers rather than receiving "
                    "customers at its business address. It should configure a service "
                    "area based on the cities, postal codes, or other permitted areas it "
                    "actually serves, and should hide its address when customers cannot "
                    "visit the business there. Service areas must not be used to create "
                    "a profile for every market or to imply coverage that is not offered."
                ),
                official_source_url="https://support.google.com/business/answer/9157481",
                source_date=source_date,
                last_verified=last_verified,
                severity="HIGH",
                applicable_to=["service_area_businesses", "hybrid_businesses"],
                examples=[
                    "A plumber who travels to homes within a defined service region",
                    "A mobile pet-grooming business that visits customers",
                    "A cleaning company that does not receive customers at its office",
                ],
                counter_examples=[
                    "Creating one profile per neighborhood solely to rank locally",
                    "Listing a broad national service area that the business does not serve",
                    "Showing a storefront address where customers are never received",
                ],
            ),
            GbpPolicyRecord(
                policy_id="GBP-POL-VO-01",
                category="Virtual office and coworking",
                title="Virtual offices and shared spaces must meet location criteria",
                description=(
                    "A virtual office is not eligible for a Business Profile when the "
                    "business does not operate there. A coworking or shared office may "
                    "qualify only when the business has a dedicated space, can receive "
                    "customers there during stated hours, and has clear permanent "
                    "signage and staff presence as required by Google's guidelines."
                ),
                official_source_url="https://support.google.com/business/answer/3038177",
                source_date=source_date,
                last_verified=last_verified,
                severity="CRITICAL",
                applicable_to=["virtual_offices", "coworking_spaces", "service_businesses"],
                examples=[
                    "A dedicated, signed office staffed by the business during published hours",
                    "A professional practice that meets customers at its permanently signed suite",
                ],
                counter_examples=[
                    "A mail-forwarding address with no business operations",
                    "A hot desk that can be booked by different businesses",
                    "A receptionist accepting mail without a dedicated customer-facing office",
                ],
            ),
            GbpPolicyRecord(
                policy_id="GBP-POL-LEADGEN-01",
                category="Lead-generation and deceptive practices",
                title="Do not create profiles solely for lead generation or misdirection",
                description=(
                    "Profiles must represent eligible businesses and may not be used "
                    "solely as lead-generation pages, referral pages, or locations for "
                    "another business. Do not impersonate another organization, redirect "
                    "customers deceptively, manipulate categories, or use false claims "
                    "to obtain calls, visits, or reviews."
                ),
                official_source_url="https://support.google.com/business/answer/3038177",
                source_date=source_date,
                last_verified=last_verified,
                severity="CRITICAL",
                applicable_to=["all_businesses", "agencies", "lead_generation_companies"],
                examples=[
                    "A profile managed for the actual operating business",
                    "A franchise location represented under its authorized business identity",
                    "A marketing agency managing a client's genuine profile with authorization",
                ],
                counter_examples=[
                    "A city-specific profile that only forwards leads to unrelated providers",
                    "A fake local office created to collect calls for a national company",
                    "A profile using another company's name or branding without authorization",
                ],
            ),
            GbpPolicyRecord(
                policy_id="GBP-POL-DUP-01",
                category="Duplicate profiles",
                title="Maintain one profile per business and eligible location",
                description=(
                    "Do not create more than one Business Profile for the same business "
                    "at the same location. Duplicate profiles can split reviews and "
                    "ranking signals and may be removed or merged. Separate profiles "
                    "may be appropriate for genuinely distinct eligible locations or "
                    "departments only when Google's criteria are met."
                ),
                official_source_url="https://support.google.com/business/answer/3038177",
                source_date=source_date,
                last_verified=last_verified,
                severity="HIGH",
                applicable_to=["all_businesses", "multi_location_businesses", "agencies"],
                examples=[
                    "One profile for one eligible retail location",
                    "Separate profiles for genuinely distinct, staffed branches",
                    "A single profile updated after a business moves location",
                ],
                counter_examples=[
                    "Two profiles for the same address to target different keywords",
                    "A duplicate profile created after a name change",
                    "Multiple profiles for one service-area business by city",
                ],
            ),
            GbpPolicyRecord(
                policy_id="GBP-POL-MISREP-01",
                category="Business eligibility",
                title="Represent the business accurately and avoid misrepresentation",
                description=(
                    "Business Profile content must be truthful, current, and not "
                    "misleading. The profile must represent the actual business, its "
                    "location or service area, contact details, categories, ownership, "
                    "and offerings. Fraudulent, impersonating, or materially deceptive "
                    "information is not permitted."
                ),
                official_source_url="https://support.google.com/business/answer/3038177",
                source_date=source_date,
                last_verified=last_verified,
                severity="CRITICAL",
                applicable_to=["all_businesses", "representatives", "agencies"],
                examples=[
                    "Using the legal or public-facing name customers actually recognize",
                    "Updating hours and contact information when they change",
                    "Using a category that accurately describes the primary business",
                ],
                counter_examples=[
                    "Claiming to be an authorized branch without authorization",
                    "Using fabricated credentials, affiliations, or locations",
                    "Publishing misleading hours to capture searches",
                ],
            ),
            GbpPolicyRecord(
                policy_id="GBP-POL-INACCURATE-01",
                category="Business eligibility",
                title="Business information must be accurate and verifiable",
                description=(
                    "A profile must contain accurate information that can be verified "
                    "through the business's real-world operations. Inaccurate addresses, "
                    "phone numbers, websites, hours, categories, or service areas can "
                    "mislead customers and may result in edits, suspension, or removal."
                ),
                official_source_url="https://support.google.com/business/answer/3038177",
                source_date=source_date,
                last_verified=last_verified,
                severity="HIGH",
                applicable_to=["all_businesses", "storefronts", "service_area_businesses"],
                examples=[
                    "A phone number answered by the represented business",
                    "Hours that match the times customers can actually obtain service",
                    "A website that belongs to and describes the represented business",
                ],
                counter_examples=[
                    "A call-tracking number that routes to an unrelated company",
                    "Permanently closed businesses presented as open",
                    "A website or phone number belonging to a lead broker",
                ],
            ),
        ]

    def seed_db(self, db_conn: sqlite3.Connection | None = None) -> None:
        conn = db_conn or self._conn
        with self._lock:
            conn.execute(self._SCHEMA)
            sql = """
                INSERT INTO policies (
                    policy_id, category, title, description, official_source_url,
                    source_date, last_verified, severity, applicable_to_json,
                    examples_json, counter_examples_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(policy_id) DO UPDATE SET
                    category=excluded.category,
                    title=excluded.title,
                    description=excluded.description,
                    official_source_url=excluded.official_source_url,
                    source_date=excluded.source_date,
                    last_verified=excluded.last_verified,
                    severity=excluded.severity,
                    applicable_to_json=excluded.applicable_to_json,
                    examples_json=excluded.examples_json,
                    counter_examples_json=excluded.counter_examples_json
            """
            values = [
                (
                    p.policy_id,
                    p.category,
                    p.title,
                    p.description,
                    p.official_source_url,
                    p.source_date,
                    p.last_verified,
                    p.severity,
                    json.dumps(p.applicable_to, ensure_ascii=False),
                    json.dumps(p.examples, ensure_ascii=False),
                    json.dumps(p.counter_examples, ensure_ascii=False),
                )
                for p in self.load_default_policies()
            ]
            conn.executemany(sql, values)
            conn.commit()

    @classmethod
    def _record_from_row(cls, row: sqlite3.Row) -> GbpPolicyRecord:
        return GbpPolicyRecord(
            policy_id=row["policy_id"],
            category=row["category"],
            title=row["title"],
            description=row["description"],
            official_source_url=row["official_source_url"],
            source_date=row["source_date"],
            last_verified=row["last_verified"],
            severity=row["severity"],
            applicable_to=json.loads(row["applicable_to_json"]),
            examples=json.loads(row["examples_json"]),
            counter_examples=json.loads(row["counter_examples_json"]),
        )

    def get_policy(self, policy_id: str) -> Optional[GbpPolicyRecord]:
        if not isinstance(policy_id, str) or not policy_id.strip():
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM policies WHERE policy_id = ?", (policy_id.strip(),)
            ).fetchone()
        return self._record_from_row(row) if row else None

    def list_policies(self, category: Optional[str] = None) -> list[GbpPolicyRecord]:
        with self._lock:
            if category is None:
                rows = self._conn.execute(
                    "SELECT * FROM policies ORDER BY policy_id"
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM policies WHERE category = ? ORDER BY policy_id",
                    (category,),
                ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def get_policy_for_finding(self, violation_key: str) -> Optional[GbpPolicyRecord]:
        if not isinstance(violation_key, str) or not violation_key.strip():
            return None

        normalized = violation_key.strip().upper().replace("_", "-").replace(" ", "-")
        if normalized.startswith("GBP-POL-"):
            return self.get_policy(normalized)

        aliases = {
            "NAME": "GBP-POL-NAME-01",
            "BUSINESS-NAME": "GBP-POL-NAME-01",
            "KEYWORD-STUFFING": "GBP-POL-NAME-01",
            "ADDRESS": "GBP-POL-ADDR-01",
            "LOCATION": "GBP-POL-ADDR-01",
            "SAB": "GBP-POL-SAB-01",
            "SERVICE-AREA": "GBP-POL-SAB-01",
            "VIRTUAL-OFFICE": "GBP-POL-VO-01",
            "COWORKING": "GBP-POL-VO-01",
            "FLEX-HUB": "GBP-POL-VO-01",
            "LEAD-GEN": "GBP-POL-LEADGEN-01",
            "LEADGEN": "GBP-POL-LEADGEN-01",
            "DUPLICATE": "GBP-POL-DUP-01",
            "DUPLICATES": "GBP-POL-DUP-01",
            "MISREPRESENTATION": "GBP-POL-MISREP-01",
            "INACCURATE": "GBP-POL-INACCURATE-01",
            "PARCEL": "GBP-POL-ADDR-01",
            "DROP-OFF": "GBP-POL-ADDR-01",
        }
        policy_id = aliases.get(normalized)
        return self.get_policy(policy_id) if policy_id else None
