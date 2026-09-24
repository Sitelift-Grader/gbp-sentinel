"""Unit tests for DiscoveryEngine and ReportGenerator modules."""

from __future__ import annotations

import unittest
from pathlib import Path

from gbp_sentinel import config, db_v2
from gbp_sentinel.discovery import DiscoveryEngine, UNKNOWN
from gbp_sentinel.report_generator import ReportGenerator


class TestDiscoveryAndReporting(unittest.TestCase):
    def setUp(self):
        self.db_path = str(config.DATA_DIR / "sentinel_v2.db")
        self.discovery = DiscoveryEngine(
            location="Utrecht",
            radius_km=30.0,
            search_terms=["slotenmaker", "loodgieter"],
            db_path=self.db_path,
        )
        self.report_gen = ReportGenerator(self.db_path)

    def test_discovery_query_builder(self):
        queries = self.discovery.build_search_queries()
        self.assertIn("slotenmaker Utrecht", queries)
        self.assertIn("loodgieter Utrecht", queries)

    def test_discovery_format_profile_strict_unknown(self):
        # Empty / partial profile
        raw = {
            "name": "Test Slotenmaker",
            "url": "https://maps.google.com/?cid=12345",
        }
        formatted = self.discovery.format_profile(raw)
        self.assertEqual(formatted["business_name"], "Test Slotenmaker")
        self.assertEqual(formatted["google_maps_url"], "https://maps.google.com/?cid=12345")
        self.assertEqual(formatted["phone"], UNKNOWN)
        self.assertEqual(formatted["address"], UNKNOWN)
        self.assertEqual(formatted["website"], UNKNOWN)
        self.assertEqual(formatted["rating"], UNKNOWN)
        self.assertEqual(formatted["review_count"], UNKNOWN)
        self.assertEqual(formatted["coordinates"], UNKNOWN)

    def test_discovery_ingest(self):
        mock_profiles = [
            {
                "place_identifier": "TEST-PLACE-001",
                "business_name": "Test Loodgieter Utrecht 24/7",
                "address": "Oudegracht 100, 3511 AX Utrecht",
                "phone": "+31 30 999 8888",
                "website": "https://www.test-loodgieter-utrecht.nl",
                "category": "Plumber",
                "rating": 4.5,
                "review_count": 12,
            }
        ]
        res = self.discovery.ingest_to_db(mock_profiles)
        self.assertGreaterEqual(res["inserted_businesses"] + res["updated_businesses"], 1)
        self.assertGreaterEqual(res["snapshots_created"], 1)

    def test_report_generation_network(self):
        # Generate report for network 1
        report = self.report_gen.generate_network_report(1)
        self.assertIn("## Executive summary", report)
        self.assertIn("## Network overview", report)
        self.assertIn("## Individual profiles", report)
        self.assertIn("## Network relationships", report)
        self.assertIn("## Policy mapping", report)
        self.assertIn("## Recommended action", report)
        self.assertIn("Consider submitting this evidence through Google's official reporting process for review.", report)

    def test_report_generation_case(self):
        # Generate report for case 1
        report = self.report_gen.generate_case_report(1)
        self.assertIn("## Executive summary", report)
        self.assertIn("## Recommended action", report)
        self.assertIn("Consider submitting this evidence through Google's official reporting process for review.", report)


if __name__ == "__main__":
    unittest.main()
