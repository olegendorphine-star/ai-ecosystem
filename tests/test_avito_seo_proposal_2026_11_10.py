"""Offline copy-only check: SEO proposal MUST NOT alter live Avito feed."""
import copy
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
PRODUCTION = BASE / "docs" / "avito-feed.xml"
PROPOSAL = BASE / "reference" / "avito-seo-proposal-2026-11-10.xml"
IDS = (
    "ai-assistant-memory-moscow-001",
    "ai-assistant-memory-spb-001",
    "ai-assistant-memory-surgut-001",
    "ai-assistant-memory-chita-001",
)

def read_ads(path):
    root = ET.parse(path).getroot()
    assert root.tag == "Ads" and root.attrib.get("formatVersion") == "3"
    ads = root.findall("Ad")
    return root, ads

class AvitoSEOProposalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_root, cls.base = read_ads(PRODUCTION)
        cls.proposal_root, cls.proposal = read_ads(PROPOSAL)

    def test_four_original_records_order_and_ids(self):
        self.assertEqual([x.findtext("Id") for x in self.base], list(IDS))
        self.assertEqual([x.findtext("Id") for x in self.proposal], list(IDS))
        self.assertEqual(len(self.proposal), 4)

    def test_only_title_and_description_change(self):
        for base, proposed in zip(self.base, self.proposal):
            old = copy.deepcopy(base)
            new = copy.deepcopy(proposed)
            for node in (old, new):
                for field in ("Title", "Description"):
                    element = node.find(field)
                    self.assertIsNotNone(element)
                    node.remove(element)
            self.assertEqual(ET.tostring(old, encoding="unicode"),
                             ET.tostring(new, encoding="unicode"))
            self.assertNotEqual(base.findtext("Title"), proposed.findtext("Title"))
            self.assertNotEqual(base.findtext("Description"), proposed.findtext("Description"))

    def test_title_short_and_content_plain_and_readable(self):
        for proposed in self.proposal:
            title = proposed.findtext("Title")
            description = proposed.findtext("Description")
            self.assertGreaterEqual(len(title), 25)
            self.assertLessEqual(len(title), 50)
            self.assertGreaterEqual(len(description), 900)
            self.assertLessEqual(len(description), 2300)
            self.assertFalse(re.search(r"https?://|@\w+|[!]{2,}|[#]{2,}", title))
            self.assertIn("5 000 ₽", description)
            self.assertIn("30 000 ₽", description)
            self.assertIn("150 000 ₽", description)
            self.assertIn("удалённо", description.lower())

    def test_moscow_and_spb_copy_stays_identical(self):
        for field in ("Title", "Description"):
            self.assertEqual(self.proposal[0].findtext(field),
                             self.proposal[1].findtext(field))

    def test_no_price_image_category_or_fee_changes(self):
        for base, proposal in zip(self.base, self.proposal):
            self.assertEqual(base.findtext("Price"), proposal.findtext("Price"))
            self.assertEqual(base.findtext("AdStatus"), proposal.findtext("AdStatus"))
            self.assertEqual(base.findtext("ListingFee"), proposal.findtext("ListingFee"))
            self.assertEqual(base.findtext("Address"), proposal.findtext("Address"))
            self.assertEqual(len(proposal.findall("./Images/Image")), 6)
            self.assertEqual([i.attrib["url"] for i in base.findall("./Images/Image")],
                             [i.attrib["url"] for i in proposal.findall("./Images/Image")])

if __name__ == "__main__":
    unittest.main()
