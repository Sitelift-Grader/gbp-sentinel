import unittest
from gbp_sentinel.chain_auditor import ChainAuditor


class TestChainAuditor(unittest.TestCase):

    def setUp(self):
        self.auditor = ChainAuditor()

    def test_audit_branch_detects_financieel_fit_stuffing(self):
        gbp_listing = {
            "name": "Financieel Fit Weert I Marc op 't Roodt - Hypotheken, Verzekeringen & Financieel Advies",
            "url": "https://www.google.com/maps/place/Financieel+Fit+Weert"
        }
        branch_meta = {
            "url": "https://www.financieelfit.nl/vestigingen/weert/",
            "h1": "Financieel Fit | Weert",
            "schema_name": "Financieel Fit Weert",
            "city": "Weert"
        }

        res = self.auditor.audit_branch(gbp_listing, branch_meta)
        self.assertEqual(res["action"], "RENAME")
        self.assertEqual(res["proposed_name"], "Financieel Fit | Weert")
        self.assertIn("Marc op 't Roodt", res["stuffed_parts"])
        self.assertIn("Hypotheken Verzekeringen & Financieel Advies", res["stuffed_parts"])

    def test_audit_branch_clean_profile_retained(self):
        gbp_listing = {
            "name": "Financieel Fit | Weert",
            "url": "https://www.google.com/maps/place/Financieel+Fit+Weert"
        }
        branch_meta = {
            "url": "https://www.financieelfit.nl/vestigingen/weert/",
            "h1": "Financieel Fit | Weert",
            "schema_name": "Financieel Fit Weert",
            "city": "Weert"
        }

        res = self.auditor.audit_branch(gbp_listing, branch_meta)
        self.assertEqual(res["action"], "KEEP")
        self.assertEqual(res["proposed_name"], "Financieel Fit | Weert")
        self.assertEqual(len(res["stuffed_parts"]), 0)


if __name__ == "__main__":
    unittest.main()
