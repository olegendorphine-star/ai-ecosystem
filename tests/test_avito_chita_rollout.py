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

    def test_moscow_matches_published_reference(self):
        current = copy.deepcopy(self.ads[0])
        published = copy.deepcopy(ET.parse(MOSCOW_REFERENCE).getroot().find("Ad"))
        current.tail = published.tail = None
        self.assertEqual(ET.tostring(current), ET.tostring(published))
        self.assertEqual(current.findtext("AvitoId"), "8347570435")

    def test_chita_remote_offer_and_prices(self):
        chita = self.ads[3]
        self.assertEqual(chita.findtext("Title"), "Персональный ИИ-ассистент и автоматизация")
        self.assertIsNone(chita.find("AvitoId"))
        self.assertEqual(chita.findtext("Place"), "Удалённо")
        self.assertEqual(chita.findtext("Price"), "5000")
        prices = chita.findall("./PriceList/Service/ServicePrice")
        self.assertEqual([p.text for p in prices], ["5000", "30000", "150000"])
        self.assertTrue(all(s.findtext("ServiceStartingPrice") == "Да"
                            for s in chita.findall("./PriceList/Service")))
        desc = chita.findtext("Description") or ""
        self.assertIn("Читы", desc)
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
