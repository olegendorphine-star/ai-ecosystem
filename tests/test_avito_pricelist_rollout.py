"""Offline safeguards for multi-city Avito feed and SPb PriceList."""
import unittest
import copy
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "docs" / "avito-feed.xml"
MOSCOW_REFERENCE = ROOT / "reference" / "avito-successful-moscow-2026-11-05.xml"


class RolloutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current = ET.parse(LIVE).getroot()
        cls.ads = cls.current.findall("Ad")
        cls.reference = ET.parse(MOSCOW_REFERENCE).getroot().find("Ad")

    def test_original_two_ads_preserved(self):
        self.assertGreaterEqual(len(self.ads), 2)
        self.assertEqual([x.findtext("Id") for x in self.ads[:2]],
            ["ai-assistant-memory-moscow-001", "ai-assistant-memory-spb-001"])
        self.assertEqual(len({x.findtext('Id') for x in self.ads}), len(self.ads))

    def test_surgut_ad_and_pricelist(self):
        found = [x for x in self.ads if x.findtext('Id') == 'ai-assistant-memory-surgut-001']
        self.assertEqual(len(found), 1)
        s = found[0]
        self.assertEqual(s.findtext('Address'), 'Сургут')
        self.assertEqual(s.findtext('Price'), '5000')
        self.assertIsNone(s.find('AvitoId'))
        self.assertEqual([x.findtext('ServicePrice') for x in s.findall('./PriceList/Service')],
                         ['5000', '30000', '150000'])
        self.assertEqual(len(s.findall('./Images/Image')), 6)

    def test_moscow_preserves_published_core_and_adds_same_pricelist(self):
        actual = self.ads[0]
        original = self.reference
        for field in ("Id", "AvitoId", "Category", "ServiceType",
                      "ServiceSubtype", "ServiceSubspecies", "Specialty",
                      "WhatServices", "Specialisation", "Price", "Address",
                      "ListingFee", "AdStatus", "WorkingWithAI"):
            self.assertEqual(actual.findtext(field), original.findtext(field), field)
        self.assertEqual([x.attrib["url"] for x in actual.findall("./Images/Image")],
                         [x.attrib["url"] for x in original.findall("./Images/Image")])
        self.assertEqual([x.findtext("ServicePrice") for x in
                          actual.findall("./PriceList/Service")], ["5000", "30000", "150000"])

    def test_spb_preserves_original_identity_and_city(self):
        self.assertEqual(self.ads[0].findtext("Address"), "Москва")
        self.assertEqual(self.ads[1].findtext("Address"), "Санкт-Петербург")
        self.assertEqual(self.ads[0].findtext("AvitoId"), "8347570435")
        self.assertIsNone(self.ads[1].find("AvitoId"))

    def test_spb_three_price_rows(self):
        prices = self.ads[1].findall("./PriceList/Service/ServicePrice")
        self.assertEqual([int(p.text) for p in prices], [5000, 30000, 150000])
        self.assertEqual(len(self.ads[1].findall("./PriceList/Service")), 3)

    def test_price_from_and_unit(self):
        services = self.ads[1].findall("./PriceList/Service")
        self.assertTrue(all(x.findtext("ServiceStartingPrice") == "Да" for x in services))
        self.assertTrue(all(x.findtext("ServicePriceType") == "за услугу" for x in services))

    def test_both_ads_no_paid_promotion(self):
        for ad in self.ads:
            self.assertEqual(ad.findtext("Price"), "5000")
            self.assertEqual(ad.findtext("ListingFee"), "Package")
            self.assertEqual(ad.findtext("AdStatus"), "Free")
            self.assertIsNone(ad.find("DateEnd"))
            self.assertIsNone(ad.find("Promo"))

    def test_all_six_original_images_present_for_each(self):
        i1 = [x.attrib.get("url") for x in self.ads[0].findall("./Images/Image")]
        i2 = [x.attrib.get("url") for x in self.ads[1].findall("./Images/Image")]
        self.assertEqual(len(i1), 6)
        self.assertEqual(i1, i2)
        self.assertTrue(all(u.startswith("https://olegendorphine-star.github.io/") for u in i1))

    def test_unchanged_core_fields_city_excluded(self):
        fields = ["Category", "ServiceType", "ServiceSubtype", "ServiceSubspecies",
                  "Specialty", "WhatServices", "Specialisation", "Place", "WorkWithContract",
                  "Consultations", "Prepayment", "TechnicalSupport", "WorkingWithAI",
                  "ContactMethod", "ListingFee", "Images", "Price",
                  "AllowEmail", "AdStatus"]
        for tag in fields:
            self.assertEqual(ET.tostring(self.ads[0].find(tag)),
                             ET.tostring(self.ads[1].find(tag)), tag)

if __name__ == "__main__":
    unittest.main()
