"""Offline safeguards for four-city Avito feed and Chita launch."""
import copy
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
FEED = BASE / "docs" / "avito-feed.xml"
MOSCOW_REFERENCE = BASE / "reference" / "avito-successful-moscow-2026-11-05.xml"


class ChitaLaunchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ads = ET.parse(FEED).getroot().findall("Ad")

    def test_four_stable_unique_ads_and_cities(self):
        self.assertEqual([a.findtext("Id") for a in self.ads], [
            "ai-assistant-memory-moscow-001", "ai-assistant-memory-spb-001",
            "ai-assistant-memory-surgut-001", "ai-assistant-memory-chita-001",
        ])
        self.assertEqual([a.findtext("Address") for a in self.ads],
                         ["Москва", "Санкт-Петербург", "Сургут", "Чита"])

    def test_moscow_preserves_published_identity_and_core_fields(self):
        current = self.ads[0]
        published = ET.parse(MOSCOW_REFERENCE).getroot().find("Ad")
        protected = ("Id", "AvitoId", "Category", "ServiceType", "ServiceSubtype",
                     "ServiceSubspecies", "Specialty", "WhatServices",
                     "Specialisation", "Place", "Price", "ListingFee", "AdStatus",
                     "Address", "WorkingWithAI")
        for key in protected:
            self.assertEqual(current.findtext(key), published.findtext(key), key)
        self.assertEqual([i.attrib["url"] for i in current.findall("./Images/Image")],
                         [i.attrib["url"] for i in published.findall("./Images/Image")])
        self.assertEqual(current.findtext("AvitoId"), "8347570435")

    def test_chita_remote_offer_and_prices(self):
        chita = self.ads[3]
        self.assertEqual(chita.findtext("Title"), "ИИ-ассистент для бизнеса и документов")
        self.assertIsNone(chita.find("AvitoId"))
        self.assertEqual(chita.findtext("Place"), "Удалённо")
        self.assertEqual(chita.findtext("Price"), "5000")
        prices = chita.findall("./PriceList/Service/ServicePrice")
        self.assertEqual([p.text for p in prices], ["5000", "30000", "150000"])
        self.assertTrue(all(s.findtext("ServiceStartingPrice") == "Да"
                            for s in chita.findall("./PriceList/Service")))
        desc = chita.findtext("Description") or ""
        self.assertIn("Чите", desc)
        self.assertIn("30 000 ₽", desc)
        self.assertNotIn("Сургута", desc)
        self.assertNotIn("Санкт-Петербурга", desc)

    def test_all_ads_package_only_and_no_promotion(self):
        for ad in self.ads:
            self.assertEqual(ad.findtext("ListingFee"), "Package")
            self.assertEqual(ad.findtext("AdStatus"), "Free")
            self.assertEqual(ad.findtext("Price"), "5000")
            self.assertIsNone(ad.find("Promo"))
            self.assertIsNone(ad.find("DateEnd"))

    def test_six_same_public_images_no_drive(self):
        original = [x.attrib["url"] for x in self.ads[0].findall("./Images/Image")]
        self.assertEqual(len(original), 6)
        for ad in self.ads:
            image_urls = [x.attrib["url"] for x in ad.findall("./Images/Image")]
            self.assertEqual(image_urls, original)
            self.assertTrue(all(u.startswith("https://olegendorphine-star.github.io/ai-ecosystem/images/avito/")
                                for u in image_urls))


if __name__ == "__main__":
    unittest.main()
