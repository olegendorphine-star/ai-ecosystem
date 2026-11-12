import pathlib
import unittest
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIVE = ROOT / "docs/avito-feed.xml"
STAGED = ROOT / "reference/avito-feed-five-ads-staging-2026-11-12.xml"

class FifthAvitoAdTest(unittest.TestCase):
    def test_preserve_existing_and_add_one(self):
        old = ET.parse(ROOT / "reference/avito-seo-proposal-2026-11-10.xml").getroot().findall("Ad")
        new = ET.parse(STAGED).getroot().findall("Ad")
        self.assertEqual(LIVE.read_bytes(), STAGED.read_bytes())
        self.assertEqual(len(old), 4)
        self.assertEqual(len(new), 5)
        for previous, current in zip(old, new):
            self.assertEqual(ET.tostring(previous), ET.tostring(current))
        ids = [ad.findtext("Id") for ad in new]
        self.assertEqual(len(ids), len(set(ids)))
        fifth = new[-1]
        self.assertEqual(fifth.findtext("Address"), "Красноярск")
        self.assertEqual(fifth.findtext("ListingFee"), "Package")
        self.assertEqual(fifth.findtext("Price"), "3000")
        self.assertNotIn("AvitoId", [x.tag for x in fifth])
        self.assertIn("Excel", fifth.findtext("Title"))

if __name__ == "__main__":
    unittest.main()
