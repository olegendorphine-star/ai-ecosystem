"""Offline SEO checks: 4 Avito ads stable, no changed ids/prices/categories/photos."""
from __future__ import annotations
import copy
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "docs" / "avito-feed.xml"
PROPOSAL = ROOT / "reference" / "avito-seo-proposal-2026-11-10.xml"
CITIES = ["Москва", "Санкт-Петербург", "Сургут", "Чита"]
IDS = [
    "ai-assistant-memory-moscow-001",
    "ai-assistant-memory-spb-001",
    "ai-assistant-memory-surgut-001",
    "ai-assistant-memory-chita-001",
]
TITLE_SUBJECTS = ["Автоматизация", "ИИ-ассистент", "ИИ-ассистент", "ИИ-ассистент"]

def parse(path):
    root = ET.parse(path).getroot()
    assert root.tag == "Ads" and root.attrib.get("formatVersion") == "3"
    return root.findall("Ad")

class SEOTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.production = parse(PRODUCTION)
        cls.proposed = parse(PROPOSAL)

    def test_stable_ids_cities_count(self):
        self.assertEqual([x.findtext("Id") for x in self.proposed], IDS)
        self.assertEqual([x.findtext("Address") for x in self.proposed], CITIES)
        self.assertEqual(len(self.production), 4)

    def test_four_unique_high_intent_titles(self):
        titles = [x.findtext("Title", "") for x in self.proposed]
        self.assertEqual(len(set(titles)), 4)
        for title, subject in zip(titles, TITLE_SUBJECTS):
            self.assertLessEqual(len(title), 50)
            self.assertGreaterEqual(len(title), 27)
            self.assertIn(subject, title)
            self.assertNotIn("!", title)

    def test_four_distinct_useful_descriptions(self):
        texts = [x.findtext("Description", "") for x in self.proposed]
        self.assertEqual(len(set(texts)), 4)
        for text in texts:
            self.assertGreaterEqual(len(text), 1150)
            self.assertLessEqual(len(text), 2000)
            head = text[:310]
            for value in ("5 000 ₽", "30 000 ₽"):
                self.assertIn(value, head)
            self.assertIn("150 000 ₽", text)
            self.assertIn("Напишите", text)
            self.assertTrue("API Авито" in text or "официальный API Авито" in text)
            self.assertIn("удалённо", text.lower() if "удалённо" in text.lower() else text.lower().replace("дистанционно","удалённо"))

    def test_no_mutation_to_identity_category_fees_images(self):
        for old, proposed in zip(self.production, self.proposed):
            for tag in ("Id", "AvitoId", "Category", "ServiceType", "ServiceSubtype",
                        "ServiceSubspecies", "Specialty", "WhatServices",
                        "Specialisation", "WorkingWithAI", "Place", "Price", 
                        "AdStatus", "ListingFee", "Address"):
                self.assertEqual(old.findtext(tag), proposed.findtext(tag), (old.findtext("Id"),tag))
            self.assertEqual(
                [x.attrib["url"] for x in old.findall("./Images/Image")],
                [x.attrib["url"] for x in proposed.findall("./Images/Image")])
            self.assertEqual(len(proposed.findall("./Images/Image")),6)

    def test_only_content_fields_and_moscow_pricelist_change(self):
        for idx,(old, new) in enumerate(zip(self.production, self.proposed)):
            a,b=copy.deepcopy(old),copy.deepcopy(new)
            for item in (a,b):
                for field in ("Title","Description"):
                    elem=item.find(field)
                    self.assertIsNotNone(elem)
                    item.remove(elem)
            if idx==0:
                self.assertIsNone(a.find("PriceList"))
                self.assertIsNotNone(b.find("PriceList"))
                b.remove(b.find("PriceList"))
            self.assertEqual(
                ET.tostring(a,encoding="unicode"),ET.tostring(b,encoding="unicode"))

    def test_all_four_pricelists_exact_and_consistent(self):
        expected=[5000,30000,150000]
        for ad in self.proposed:
            services=ad.findall("./PriceList/Service")
            self.assertEqual(len(services),3)
            self.assertEqual([int(x.findtext("ServicePrice")) for x in services],expected)
            self.assertEqual(ad.findtext("AdStatus"), "Free")
            self.assertEqual(ad.findtext("ListingFee"), "Package")
            self.assertEqual(ad.findtext("Price"), "5000")

    def test_no_publication_or_extra_action_in_changes(self):
        self.assertEqual(
            [x.findtext("Id") for x in self.proposed],
            [x.findtext("Id") for x in self.production])

if __name__=="__main__":
    unittest.main()
