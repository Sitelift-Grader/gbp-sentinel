import unittest
from gbp_sentinel.name_sanitizer import NameSanitizer


class TestNameSanitizer(unittest.TestCase):

    def setUp(self):
        self.sanitizer = NameSanitizer()

    def test_nail_studio_keyword_stuffing(self):
        raw = "Biab Nagels | Ferry's Nails Studio | Nagelstudio"
        res = self.sanitizer.sanitize(raw)
        self.assertEqual(res["action"], "RENAME")
        self.assertEqual(res["clean_name"], "Ferry's Nails Studio")
        self.assertIn("Nagelstudio", res["removed_parts"])

    def test_facade_renovation_keyword_stuffing(self):
        raw = "DMS Holland | Gevelrenovatie | Gevelreiniging | Bouwbedrijf"
        res = self.sanitizer.sanitize(raw)
        self.assertEqual(res["action"], "RENAME")
        self.assertEqual(res["clean_name"], "DMS Holland")
        self.assertEqual(len(res["removed_parts"]), 3)

    def test_webdesign_geo_stuffing(self):
        raw = "Subcolors | Website laten maken Den Haag"
        res = self.sanitizer.sanitize(raw)
        self.assertEqual(res["action"], "RENAME")
        self.assertEqual(res["clean_name"], "Subcolors")

    def test_webdesign_claim_stuffing(self):
        raw = "Instant Digital | Professionele Website Laten Maken"
        res = self.sanitizer.sanitize(raw)
        self.assertEqual(res["action"], "RENAME")
        self.assertEqual(res["clean_name"], "Instant Digital")

    def test_hairdresser_emoji_stuffing(self):
        raw = "Kapper barbier Eindhoven - Salon New Age ✂"
        res = self.sanitizer.sanitize(raw)
        self.assertEqual(res["action"], "RENAME")
        self.assertEqual(res["clean_name"], "Salon New Age")

    def test_pure_keyword_spam_removals(self):
        cases = [
            "123websitelatenmakenAmsterdam",
            "123websitelatenmakenutrecht",
            "Website Laten Maken amsterdam",
            "Website laten maken Rotterdam",
            "Website maken",
            "leadgen website Den Haag"
        ]
        for c in cases:
            with self.subTest(candidate=c):
                res = self.sanitizer.sanitize(c)
                self.assertEqual(res["action"], "REMOVE")
                self.assertEqual(res["clean_name"], "")

    def test_clean_business_retained(self):
        raw = "Van Ons"
        res = self.sanitizer.sanitize(raw)
        self.assertEqual(res["action"], "KEEP")
        self.assertEqual(res["clean_name"], "Van Ons")

    def test_prefix_service_segment_stripped(self):
        raw = "Opleiding nagelstylist Amsterdam & Nagelstudio | Melanin Nails & Beauty"
        res = self.sanitizer.sanitize(raw)
        self.assertEqual(res["action"], "RENAME")
        self.assertEqual(res["clean_name"], "Melanin Nails & Beauty")
        self.assertIn("Opleiding nagelstylist Amsterdam & Nagelstudio", res["removed_parts"])


if __name__ == "__main__":
    unittest.main()
