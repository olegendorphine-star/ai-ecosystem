"""Validate staged Avito SEO rollout without hitting Avito or changing accounts."""
from __future__ import annotations
import copy
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASELINE=ROOT/"reference"/"avito-baseline-pre-seo-2026-11-10.xml"
PRODUCTION=ROOT/"docs"/"avito-feed.xml"
PROPOSAL=ROOT/"reference"/"avito-seo-proposal-2026-11-10.xml"
IDS=["ai-assistant-memory-moscow-001","ai-assistant-memory-spb-001",
     "ai-assistant-memory-surgut-001","ai-assistant-memory-chita-001"]
CITIES=["Москва","Санкт-Петербург","Сургут","Чита"]

def ads(path):
    root=ET.parse(path).getroot()
    assert root.tag=="Ads" and root.attrib.get("formatVersion")=="3"
    return root.findall("Ad")

def normalized(node):
    """Ignore indentation whitespace, but preserve every field/value/attribute."""
    return (node.tag, tuple(sorted(node.attrib.items())),
            (node.text or "").strip(), tuple(normalized(x) for x in node))

class SEOTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=ads(BASELINE)
        cls.live=ads(PRODUCTION)
        cls.proposal=ads(PROPOSAL)

    def test_exact_rollout_matches_reviewed_proposal(self):
        self.assertEqual(PRODUCTION.read_bytes(),PROPOSAL.read_bytes())

    def test_same_four_live_id_city_pairs(self):
        for arr in (self.base,self.live):
            self.assertEqual([a.findtext("Id") for a in arr],IDS)
            self.assertEqual([a.findtext("Address") for a in arr],CITIES)
            self.assertEqual(len(arr),4)

    def test_unique_search_titles_below_50(self):
        titles=[a.findtext("Title","") for a in self.live]
        self.assertEqual(len(set(titles)),4)
        for title in titles:
            self.assertTrue(29<=len(title)<=50)
            self.assertIn("ИИ",title)
            self.assertNotIn("!",title)
        self.assertTrue(titles[0].startswith("Автоматизация бизнеса с ИИ"))
        for t in titles[1:]:
            self.assertTrue(t.startswith("ИИ-ассистент"))

    def test_descriptions_specific_without_misleading_5000(self):
        texts=[a.findtext("Description","") for a in self.live]
        self.assertEqual(len(set(texts)),4)
        for text in texts:
            self.assertTrue(1250<=len(text)<=1900)
            first=text[:330]
            self.assertIn("5 000 ₽",first)
            self.assertIn("30 000 ₽",first)
            self.assertIn("150 000 ₽",text)
            self.assertIn("Напишите",text)
            self.assertIn("Авито",text)
            self.assertNotIn("100% гарантия",text)
            self.assertNotIn("Бесплатно подключим",text)
        self.assertIn("не стоимость готового",texts[0])

    def test_all_ids_price_category_location_and_six_images_unchanged(self):
        for prior,new in zip(self.base,self.live):
            for field in ("Id","AvitoId","Category","ServiceType","ServiceSubtype",
                          "ServiceSubspecies","Specialty","WhatServices",
                          "Specialisation","WorkingWithAI","Place","Price",
                          "ListingFee","AdStatus","Address","Prepayment"):
                self.assertEqual(prior.findtext(field),new.findtext(field),
                                 (prior.findtext("Id"),field))
            self.assertEqual(len(new.findall("./Images/Image")),6)
            self.assertEqual(
                [i.attrib["url"] for i in prior.findall("./Images/Image")],
                [i.attrib["url"] for i in new.findall("./Images/Image")])

    def test_changes_only_copy_and_moscow_price_list(self):
        for index,(prior,new) in enumerate(zip(self.base,self.live)):
            a,b=copy.deepcopy(prior),copy.deepcopy(new)
            for obj in (a,b):
                for field in ("Title","Description"):
                    obj.remove(obj.find(field))
            if index==0:
                self.assertIsNone(a.find("PriceList"))
                self.assertIsNotNone(b.find("PriceList"))
                b.remove(b.find("PriceList"))
            self.assertEqual(normalized(a),normalized(b))

    def test_four_matching_public_price_lists_from_verified_template(self):
        for ad in self.live:
            services=ad.findall("./PriceList/Service")
            self.assertEqual(len(services),3)
            self.assertEqual(
                [int(x.findtext("ServicePrice")) for x in services],
                [5000,30000,150000])
            self.assertEqual(ad.findtext("ListingFee"),"Package")
            self.assertEqual(ad.findtext("AdStatus"),"Free")
            self.assertEqual(ad.findtext("Price"),"5000")

    def test_no_mutation_operations_or_new_ad_sections(self):
        text=PRODUCTION.read_text()
        self.assertEqual(text.count("<Ad>"),4)
        self.assertEqual(text.count("</Ad>"),4)
        self.assertNotIn("<AdStatus>Paid</AdStatus>",text)
        self.assertNotIn("<ListingFee>Single</ListingFee>",text)
        self.assertNotIn("<Promotion>",text)

if __name__=="__main__":
    unittest.main()
